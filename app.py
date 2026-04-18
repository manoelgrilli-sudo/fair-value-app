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

# --- MOTOR DE EXTRAÇÃO E PROCESSAMENTO ---
def extrair_dados_especificos(f_binario):
    try:
        texto = extract_text(f_binario)
        texto_limpo = " ".join(texto.split())
        info = {"NF": "S/N", "V": 0.0, "Desc": "", "Data": "01/01/2026"}
        
        nf_m = re.search(r"Número da NFS-e\s*(\d+)", texto_limpo)
        if nf_m: info["NF"] = nf_m.group(1)

        data_m = re.search(r"(\d{2}/\d{2}/\d{4})", texto_limpo)
        if data_m: info["Data"] = data_m.group(1)

        if "Descrição do Serviço" in texto_limpo:
            inicio = texto_limpo.find("Descrição do Serviço") + len("Descrição do Serviço")
            fim_idx = texto_limpo.upper().find("TRIBUTAÇÃO", inicio)
            if fim_idx == -1: fim_idx = inicio + 250 
            info["Desc"] = texto_limpo[inicio:fim_idx].strip()

        val_m = re.search(r"Valor do Serviço\s*R\$\s*([\d.,]+)", texto_limpo)
        if val_m: info["V"] = float(val_m.group(1).replace(".", "").replace(",", "."))
            
        return info
    except: return None

def fmt(v): return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- INTERFACE E LÓGICA PRINCIPAL ---
if check_password():
    st.set_page_config(page_title="Fair Value - Rateio", layout="wide")
    st.title("🏛️ Fair Value - Rateio DAS")

    c1, c2 = st.columns(2)
    with c1: arq_das_in = st.file_uploader("1. Guia DAS (PDF)", type=["pdf"])
    with c2: arqs_nfs_in = st.file_uploader("2. Notas Fiscais (ZIP/PDF)", type=["zip", "pdf"], accept_multiple_files=True)

    if arq_das_in and arqs_nfs_in:
        nfs_lidas = []
        for item in arqs_nfs_in:
            if item.name.lower().endswith('.zip'):
                with zipfile.ZipFile(item) as z:
                    for nome_f in z.namelist():
                        if nome_f.lower().endswith('.pdf'):
                            with z.open(nome_f) as f:
                                nfs_lidas.append(extrair_dados_especificos(io.BytesIO(f.read())))
            else:
                nfs_lidas.append(extrair_dados_especificos(item))

        nfs_lidas = [n for n in nfs_lidas if n is not None]
        nfs_lidas.sort(key=lambda x: datetime.strptime(x['Data'], '%d/%m/%Y'))
        
        try:
            txt_das = extract_text(arq_das_in)
            m_das = re.search(r"Valor Total do Documento\s*([\d.,]+)", txt_das)
            total_das = float(m_das.group(1).replace(".", "").replace(",", "."))
        except: total_das = 0.0

        st.markdown("---")
        validado = []
        
        st.subheader("🔍 Conferência e Identificação")
        for i, nota in enumerate(nfs_lidas):
            col1, col2, col3 = st.columns([1, 1, 2])
            col1.info(f"📅 {nota['Data']} | NF: {nota['NF']}")
            col2.write(f"**{fmt(nota['V'])}**")
            nome = col3.text_input(f"Quem é o Prestador?", key=f"p_{i}")
            
            st.caption(f"📝 **Descrição da NF:** {nota['Desc']}")
            st.markdown("---")
            validado.append({"P": nome.upper().strip(), "V": nota["V"], "NF": nota["NF"], "Data": nota["Data"]})

        if st.button("📊 GERAR RELATÓRIO PDF FINAL"):
            df = pd.DataFrame(validado)
            
            # AGRUPAMENTO POR PRESTADOR (CORREÇÃO DO NICOLLAS)
            resumo = df.groupby("P")["V"].sum().reset_index()
            total_f = resumo["V"].sum()
            resumo["R"] = (resumo["V"] / total_f) * total_das
            
            # Detalhamento cronológico
            df['dt_obj'] = pd.to_datetime(df['Data'], format='%d/%m/%Y')
            df_detalhe = df.sort_values('dt_obj')

            pdf = FPDF()
            pdf.add_page()
            
            # Tente carregar a logo se ela existir no repo
            try: pdf.image('LOGO_VERT_BLACK@4x.png', x=75, y=15, w=60); pdf.ln(50)
            except: pass
            
            # TABELA 1: CÁLCULO DE RATEIO DAS
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(190, 10, "CÁLCULO DE RATEIO DAS", ln=True, align='C')
            pdf.ln(5)
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(80, 10, "PRESTADOR", 1); pdf.cell(55, 10, "FATURAMENTO", 1, 0, 'C'); pdf.cell(55, 10, "RATEIO DAS", 1, 1, 'C')
            pdf.set_font("Arial", '', 10)
            for _, r in resumo.iterrows():
                pdf.cell(80, 10, f" {r['P']}", 1)
                pdf.cell(55, 10, f"{fmt(r['V'])}", 1, 0, 'C')
                pdf.cell(55, 10, f"{fmt(r['R'])}", 1, 1, 'C')
            
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(80, 10, "TOTAL", 1); pdf.cell(55, 10, f"{fmt(total_f)}", 1, 0, 'C'); pdf.cell(55, 10, f"{fmt(total_das)}", 1, 1, 'C')
            
            pdf.ln(15)
            
            # TABELA 2: DETALHAMENTO POR NOTA FISCAL
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(190, 10, "DETALHAMENTO POR NOTA FISCAL", ln=True, align='L')
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(60, 10, "PRESTADOR", 1); pdf.cell(30, 10, "DATA", 1, 0, 'C'); pdf.cell(50, 10, "NÚMERO NF", 1, 0, 'C'); pdf.cell(50, 10, "VALOR NF", 1, 1, 'C')
            pdf.set_font("Arial", '', 9)
            for _, n in df_detalhe.iterrows():
                pdf.cell(60, 10, f" {n['P']}", 1)
                pdf.cell(30, 10, f"{n['Data']}", 1, 0, 'C')
                pdf.cell(50, 10, f"{n['NF']}", 1, 0, 'C')
                pdf.cell(50, 10, f"{fmt(n['V'])}", 1, 1, 'C')

            st.download_button("📥 BAIXAR RELATÓRIO FINAL", pdf.output(dest='S').encode('latin-1'), "Rateio_FairValue.pdf")
