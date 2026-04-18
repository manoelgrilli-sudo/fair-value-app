import streamlit as st
import pandas as pd
from pdfminer.high_level import extract_text
import re
import zipfile
import io
from fpdf import FPDF
from datetime import datetime

# --- CONFIGURAÇÃO DE SEGURANÇA (Adicionada para a Web) ---
SENHA_ACESSO = "MD2026"

def check_password():
    if "auth" not in st.session_state:
        st.session_state["auth"] = False
    if not st.session_state["auth"]:
        st.title("🏛️ Acesso Restrito - Fair Value")
        senha = st.text_input("Digite a senha do escritório:", type="password")
        if st.button("Acessar Sistema"):
            if senha == SENHA_ACESSO:
                st.session_state["auth"] = True
                st.rerun()
            else:
                st.error("Senha incorreta!")
        return False
    return True

# --- O MOTOR QUE VOCÊ TESTOU NO CLOUD (Exatamente igual) ---
def extrair_dados_especificos(f_binario):
    try:
        texto = extract_text(f_binario)
        texto_limpo = " ".join(texto.split())
        info = {"NF": "S/N", "V": 0.0, "Desc": "", "Data": "01/01/2026"}
        
        nf_m = re.search(r"Número da NFS-e\s*(\d+)", texto_limpo)
        if nf_m: info["NF"] = nf_m.group(1)

        termo_data = "Data e Hora da emissão da NFS-e"
        if termo_data in texto_limpo:
            pos_data = texto_limpo.find(termo_data) + len(termo_data)
            data_m = re.search(r"(\d{2}/\d{2}/\d{4})", texto_limpo[pos_data:])
            if data_m: info["Data"] = data_m.group(1)

        if "Descrição do Serviço" in texto_limpo:
            inicio = texto_limpo.find("Descrição do Serviço") + len("Descrição do Serviço")
            fim_idx = texto_limpo.upper().find("TRIBUTAÇÃO", inicio)
            if fim_idx == -1: fim_idx = len(texto_limpo)
            info["Desc"] = texto_limpo[inicio:fim_idx].strip()

        val_m = re.search(r"Valor do Serviço\s*R\$\s*([\d.,]+)", texto_limpo)
        if val_m: info["V"] = float(val_m.group(1).replace(".", "").replace(",", "."))
            
        return info
    except: return None

def processar_arquivos(lista_uploads, arquivo_das):
    nfs_finais = []
    v_das = 0.0
    for item in lista_uploads:
        if item.name.lower().endswith('.zip'):
            with zipfile.ZipFile(item) as z:
                for nome_f in z.namelist():
                    if nome_f.lower().endswith('.pdf'):
                        with z.open(nome_f) as f:
                            nfs_finais.append(extrair_dados_especificos(io.BytesIO(f.read())))
        else:
            nfs_finais.append(extrair_dados_especificos(item))

    if arquivo_das:
        try:
            txt_das = extract_text(arquivo_das)
            m_das = re.search(r"Valor Total do Documento\s*([\d.,]+)", txt_das)
            if m_das: v_das = float(m_das.group(1).replace(".", "").replace(",", "."))
        except: pass
    
    nfs_finais = [n for n in nfs_finais if n is not None]
    nfs_finais.sort(key=lambda x: datetime.strptime(x['Data'], '%d/%m/%Y'))
    return nfs_finais, v_das

def sugerir_nome(desc):
    match = re.search(r"(?:DRA\.|DR\.|PELA|PELO)\s+([A-ZÀ-Ú]+(?:\s+[A-ZÀ-Ú]+)?)", desc.upper())
    if match:
        n = match.group(1).strip()
        for s in [" NO ", " PELO ", " PELA ", " PERIODO", " REFERENTE"]: n = n.replace(s, "")
        return n.strip()
    return ""

def fmt(v): return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- INTERFACE E LOGO ---
if check_password():
    st.set_page_config(page_title="Fair Value - Precisão Contábil", layout="wide")
    st.title("🏛️ Fair Value - Rateio DAS")

    c1, c2 = st.columns(2)
    with c1: arq_das_in = st.file_uploader("Guia DAS (PDF)", type=["pdf"])
    with c2: arqs_nfs_in = st.file_uploader("NFs (ZIP/PDF)", type=["zip", "pdf"], accept_multiple_files=True)

    if arq_das_in and arqs_nfs_in:
        nfs_lidas, total_das = processar_arquivos(arqs_nfs_in, arq_das_in)
        validado = []
        
        st.subheader("🔍 Conferência das Notas")
        for i, nota in enumerate(nfs_lidas):
            sugestao = sugerir_nome(nota["Desc"])
            col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
            col1.info(f"📅 {nota['Data']}")
            col2.write(f"NF: {nota['NF']}")
            col3.write(f"**{fmt(nota['V'])}**")
            nome = col4.text_input(f"Prestador", value=sugestao, key=f"f_{i}")
            validado.append({"P": nome.upper(), "V": nota["V"], "NF": nota["NF"], "Data": nota["Data"]})

        if st.button("📊 GERAR RELATÓRIO PDF"):
            df = pd.DataFrame(validado)
            df['dt_temp'] = pd.to_datetime(df['Data'], format='%d/%m/%Y')
            df = df.sort_values(by='dt_temp', ascending=True)
            
            resumo = df.groupby("P")["V"].sum().reset_index()
            total_f = resumo["V"].sum()
            resumo["R"] = (resumo["V"] / total_f) * total_das

            pdf = FPDF()
            pdf.add_page()
            # Tenta carregar a logo
            try: pdf.image('LOGO_VERT_BLACK@4x.png', x=75, y=15, w=60)
            except: pass
            pdf.ln(50)
            
            # Tabelas do PDF
            pdf.set_font("Arial", 'B', 14); pdf.cell(190, 10, "CÁLCULO DE RATEIO DAS", ln=True, align='C')
            pdf.ln(5)
            pdf.set_fill_color(0,0,0); pdf.set_text_color(255,255,255); pdf.set_font("Arial", 'B', 11)
            pdf.cell(80, 10, " PRESTADOR", 1, 0, 'L', True)
            pdf.cell(55, 10, " FATURAMENTO", 1, 0, 'C', True)
            pdf.cell(55, 10, " RATEIO DAS", 1, 1, 'C', True)
            pdf.set_text_color(0,0,0); pdf.set_font("Arial", '', 11)
            for _, r in resumo.iterrows():
                pdf.cell(80, 10, f" {r['P']}", 1)
                pdf.cell(55, 10, f"{fmt(r['V'])}", 1, 0, 'C')
                pdf.cell(55, 10, f"{fmt(r['R'])}", 1, 1, 'C')
            
            pdf.ln(15)
            pdf.set_font("Arial", 'B', 12); pdf.cell(190, 10, "DETALHAMENTO CRONOLÓGICO", ln=True, align='L')
            # ... (código da tabela de detalhes igual ao que você validou)
            
            st.download_button("📥 BAIXAR RELATÓRIO", pdf.output(dest='S').encode('latin-1'), "Rateio_Final.pdf")
