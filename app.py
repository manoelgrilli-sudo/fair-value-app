import streamlit as st
import pandas as pd
from pdfminer.high_level import extract_text
import re
import zipfile
import io
from fpdf import FPDF
from datetime import datetime

# --- CONFIGURAÇÃO DE SEGURANÇA ---
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

# --- SEU MOTOR DE EXTRAÇÃO V8 (VALIDADO) ---
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
            # Procura o fim da descrição (geralmente antes de Tributação ou Retenções)
            fim_idx = texto_limpo.upper().find("TRIBUTAÇÃO", inicio)
            if fim_idx == -1: fim_idx = texto_limpo.upper().find("VALOR", inicio)
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

def fmt(v): return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- INTERFACE ---
if check_password():
    st.set_page_config(page_title="Fair Value - Rateio", layout="wide")
    st.title("🏛️ Fair Value - Rateio DAS")

    c1, c2 = st.columns(2)
    with c1: arq_das_in = st.file_uploader("1. Guia DAS (PDF)", type=["pdf"])
    with c2: arqs_nfs_in = st.file_uploader("2. Notas Fiscais (ZIP/PDF)", type=["zip", "pdf"], accept_multiple_files=True)

    if arq_das_in and arqs_nfs_in:
        nfs_lidas, total_das = processar_arquivos(arqs_nfs_in, arq_das_in)
        validado = []
        
        st.markdown("---")
        st.subheader("🔍 Conferência das Notas e Descrições")
        
        for i, nota in enumerate(nfs_lidas):
            # Linha principal com dados básicos
            col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
            col1.info(f"📅 {nota['Data']}")
            col2.write(f"NF: {nota['NF']}")
            col3.write(f"**{fmt(nota['V'])}**")
            
            # Campo para o nome do prestador
            nome = col4.text_input(f"Identificar Prestador (Nota {i+1})", key=f"p_{i}")
            
            # EXIBIÇÃO DA DESCRIÇÃO (O que você precisava)
            st.caption(f"**Trecho da Descrição do Serviço:** {nota['Desc'][:500]}...")
            st.markdown("---")
            
            validado.append({"P": nome.upper(), "V": nota["V"], "NF": nota["NF"], "Data": nota["Data"]})

        if st.button("📊 GERAR RELATÓRIO PDF"):
            df = pd.DataFrame(validado)
            resumo = df.groupby("P")["V"].sum().reset_index()
            total_f = resumo["V"].sum()
            resumo["R"] = (resumo["V"] / total_f) * total_das

            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(190, 10, "RATEIO DAS - FAIR VALUE", ln=True, align='C')
            pdf.ln(10)
            
            # Tabela de Rateio
            pdf.set_font("Arial", 'B', 11)
            pdf.cell(80, 10, " PRESTADOR", 1); pdf.cell(55, 10, " VALOR NF", 1, 0, 'C'); pdf.cell(55, 10, " RATEIO DAS", 1, 1, 'C')
            pdf.set_font("Arial", '', 11)
            for _, r in resumo.iterrows():
                pdf.cell(80, 10, f" {r['P']}", 1)
                pdf.cell(55, 10, f"{fmt(r['V'])}", 1, 0, 'C')
                pdf.cell(55, 10, f"{fmt(r['R'])}", 1, 1, 'C')
            
            st.download_button("📥 BAIXAR RELATÓRIO", pdf.output(dest='S').encode('latin-1'), "Rateio.pdf")
