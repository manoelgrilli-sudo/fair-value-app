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

def sugerir_nome(desc):
    # REGRA MELHORADA: Busca o nome completo após DR., DRA. ou DO(A)
    match = re.search(r"(?:DRA?\.|PARA\s+|PELO\s+|PELA\s+|AO\s+)([A-ZÀ-Ú\s]{3,30})", desc.upper())
    if match:
        nome = match.group(1).strip()
        # Limpa palavras que não fazem parte do nome
        for lixo in [" REFERENTE", " NO ", " PERÍODO", " COMPETÊNCIA", " VALOR", " CPF"]:
            if lixo in nome: nome = nome.split(lixo)[0]
        return nome.strip()
    return ""

def fmt(v): return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

if check_password():
    st.set_page_config(page_title="Fair Value", layout="wide")
    st.title("🏛️ Fair Value - Rateio DAS")
    
    c1, c2 = st.columns(2)
    with c1: arq_das_in = st.file_uploader("1. Guia DAS (PDF)", type=["pdf"])
    with c2: arqs_nfs_in = st.file_uploader("2. Notas Fiscais", type=["zip", "pdf"], accept_multiple_files=True)

    if arq_das_in and arqs_nfs_in:
        nfs_finais = []
        for item in arqs_nfs_in:
            if item.name.lower().endswith('.zip'):
                with zipfile.ZipFile(item) as z:
                    for nome_f in z.namelist():
                        if nome_f.lower().endswith('.pdf'):
                            with z.open(nome_f) as f:
                                nfs_finais.append(extrair_dados_especificos(io.BytesIO(f.read())))
            else:
                nfs_finais.append(extrair_dados_especificos(item))

        nfs_finais = [n for n in nfs_finais if n is not None]
        nfs_finais.sort(key=lambda x: datetime.strptime(x['Data'], '%d/%m/%Y'))
        
        txt_das = extract_text(arq_das_in)
        m_das = re.search(r"Valor Total do Documento\s*([\d.,]+)", txt_das)
        total_das = float(m_das.group(1).replace(".", "").replace(",", ".")) if m_das else 0.0

        st.markdown("---")
        validado = []
        for i, nota in enumerate(nfs_finais):
            sugestao = sugerir_nome(nota["Desc"])
            col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
            col1.info(f"{nota['Data']}")
            col2.write(f"NF: {nota['NF'][-5:]}")
            col3.write(f"{fmt(nota['V'])}")
            nome = col4.text_input(f"Confirmar Prestador", value=sugestao, key=f"v9_{i}")
            validado.append({"P": nome.upper(), "V": nota["V"], "NF": nota["NF"], "Data": nota["Data"]})

        if st.button("📊 GERAR PDF FINAL"):
            df = pd.DataFrame(validado)
            resumo = df.groupby("P")["V"].sum().reset_index()
            total_f = resumo["V"].sum()
            resumo["R"] = (resumo["V"] / total_f) * total_das
            
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(190, 15, "RELATÓRIO DE RATEIO - FAIR VALUE", ln=True, align='C')
            pdf.ln(5)
            
            # Tabela de Rateio
            pdf.set_fill_color(200, 200, 200)
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(80, 10, " PRESTADOR", 1, 0, 'L', True)
            pdf.cell(55, 10, " FATURAMENTO", 1, 0, 'C', True)
            pdf.cell(55, 10, " RATEIO DAS", 1, 1, 'C', True)
            
            pdf.set_font("Arial", '', 10)
            for _, r in resumo.iterrows():
                pdf.cell(80, 10, f" {r['P']}", 1)
                pdf.cell(55, 10, f" {fmt(r['V'])}", 1, 0, 'C')
                pdf.cell(55, 10, f" {fmt(r['R'])}", 1, 1, 'C')
                
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(80, 10, " TOTAL", 1, 0, 'L', True)
            pdf.cell(55, 10, f" {fmt(total_f)}", 1, 0, 'C', True)
            pdf.cell(55, 10, f" {fmt(total_das)}", 1, 1, 'C', True)

            st.download_button("📥 BAIXAR RELATÓRIO PRONTO", pdf.output(dest='S').encode('latin-1'), "Rateio_Final_FairValue.pdf")
