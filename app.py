import os
import time
import io
import re
from datetime import datetime
import pandas as pd
import streamlit as st

# SDK Oficial google-genai
from google import genai
from google.genai import types
from google.genai.errors import APIError

# Librerías para generación de PDF en ReportLab
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# -----------------------------------------------------------------------------
# 1. CONFIGURACIÓN DE PÁGINA Y CSS CORPORATIVO (ESTILO LANDING PAGE)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="EduEvalua AI - Evaluación Institucional",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    /* Reset y tipografía global */
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Inter', sans-serif;
        background-color: #F8FAFC;
        color: #1E293B;
    }
    
    /* Ocultar elementos de Streamlit por defecto */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {
        padding-top: 0rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 1400px;
    }

    /* Hero Section */
    .hero-container {
        background: linear-gradient(135deg, #0F172A 0%, #1E3A8A 100%);
        color: white;
        padding: 4rem 2rem;
        border-radius: 0 0 24px 24px;
        text-align: center;
        margin-bottom: 3rem;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
    }
    .hero-title {
        font-size: 3rem;
        font-weight: 700;
        margin-bottom: 1rem;
        letter-spacing: -0.02em;
    }
    .hero-subtitle {
        font-size: 1.25rem;
        color: #93C5FD;
        font-weight: 400;
        max-width: 800px;
        margin: 0 auto;
    }

    /* Tarjetas de Características (3 columnas) */
    .features-grid {
        display: flex;
        gap: 2rem;
        margin-bottom: 3rem;
        justify-content: center;
        flex-wrap: wrap;
    }
    .feature-card {
        background: #FFFFFF;
        padding: 2rem;
        border-radius: 12px;
        flex: 1;
        min-width: 280px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        border-top: 4px solid #2563EB;
        text-align: center;
    }
    .feature-icon {
        font-size: 2.5rem;
        margin-bottom: 1rem;
    }
    .feature-title {
        font-weight: 600;
        font-size: 1.1rem;
        color: #0F172A;
        margin-bottom: 0.5rem;
    }
    .feature-desc {
        font-size: 0.9rem;
        color: #64748B;
    }

    /* Contenedores de la App (Paneles) */
    div[data-testid="stColumn"] {
        background-color: #FFFFFF;
        padding: 2rem !important;
        border-radius: 16px !important;
        border: 1px solid #E2E8F0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }

    /* Inputs y Formularios */
    input, textarea {
        background-color: #F8FAFC !important;
        border: 1px solid #CBD5E1 !important;
        border-radius: 8px !important;
        color: #1E293B !important;
        padding: 0.75rem !important;
    }
    input:focus, textarea:focus {
        border-color: #3B82F6 !important;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2) !important;
    }
    
    /* Botones */
    div[data-testid="stButton"] button {
        background-color: #2563EB !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.75rem 1.5rem !important;
        transition: all 0.2s ease;
    }
    div[data-testid="stButton"] button:hover {
        background-color: #1D4ED8 !important;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2) !important;
    }

    /* Tarjetas de Resultados */
    .result-metric {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        margin-bottom: 1.5rem;
    }
    .result-value {
        font-size: 2.5rem;
        font-weight: 700;
        color: #2563EB;
        line-height: 1;
    }
    .result-label {
        font-size: 0.875rem;
        text-transform: uppercase;
        color: #64748B;
        font-weight: 600;
        margin-top: 0.5rem;
        letter-spacing: 0.05em;
    }
    </style>
""", unsafe_allow_html=True)

CSV_FILE = "registro_calificaciones.csv"

# -----------------------------------------------------------------------------
# 2. LÓGICA DE BACKEND (Gemini, ReportLab, Pandas)
# -----------------------------------------------------------------------------
def get_gemini_client():
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        st.error("Error de configuración: GEMINI_API_KEY no encontrada.")
        st.stop()
    return genai.Client(api_key=api_key)

def generar_evaluacion_con_reintentos(client, contents, prompt_sistema, max_retries=3):
    model_id = "gemini-2.5-flash"
    for intento in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=prompt_sistema,
                    temperature=0.2
                )
            )
            return response.text
        except APIError as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                if intento < max_retries - 1:
                    time.sleep((intento + 1) * 2)
                    continue
                return None
            elif "503" in str(e):
                if intento < max_retries - 1:
                    time.sleep(2)
                    continue
                return None
            return None
        except Exception:
            return None
    return None

def cargar_registro():
    if os.path.exists(CSV_FILE):
        try:
            return pd.read_csv(CSV_FILE, on_bad_lines='skip')
        except Exception:
            return pd.DataFrame(columns=["Docente", "Estudiante", "Puntaje", "Nota", "Fecha"])
    return pd.DataFrame(columns=["Docente", "Estudiante", "Puntaje", "Nota", "Fecha"])

def guardar_registro(df):
    df.to_csv(CSV_FILE, index=False)

def generar_pdf_informe(nombre_docente, nombre_estudiante, nota, puntaje, feedback_texto):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40,
        title=f"Informe de Evaluación - {nombre_estudiante}"
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#0F172A'), spaceAfter=15)
    body_style = ParagraphStyle('DocBody', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.HexColor('#334155'), spaceAfter=8)

    story = [Paragraph("Informe de Evaluación Institucional", title_style), Spacer(1, 10)]
    data = [
        [Paragraph("<b>Evaluador:</b>", body_style), Paragraph(nombre_docente or "No especificado", body_style)],
        [Paragraph("<b>Estudiante:</b>", body_style), Paragraph(nombre_estudiante or "No especificado", body_style)],
        [Paragraph("<b>Puntaje:</b>", body_style), Paragraph(str(puntaje), body_style)],
        [Paragraph("<b>Nota Final:</b>", body_style), Paragraph(str(nota), body_style)]
    ]
    
    t = Table(data, colWidths=[100, 420])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    
    story.append(t)
    story.append(Spacer(1, 15))
    story.append(Paragraph("<b>Retroalimentación Detallada:</b>", body_style))
    story.append(Spacer(1, 5))
    
    for linea in feedback_texto.split('\n'):
        if linea.strip():
            story.append(Paragraph(linea.strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), body_style))
        else:
            story.append(Spacer(1, 4))
            
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

def extraer_metrica(patron, texto):
    match = re.search(patron, texto, re.IGNORECASE)
    return match.group(1).strip() if match else "N/A"

# -----------------------------------------------------------------------------
# 3. INTERFAZ Y ESTRUCTURA HTML
# -----------------------------------------------------------------------------
def main():
    # Renderizado del Hero Section
    st.markdown("""
        <div class="hero-container">
            <div class="hero-title">EduEvalua AI</div>
            <div class="hero-subtitle">Plataforma de corrección y retroalimentación pedagógica automatizada. Análisis de desempeño basado en rúbricas institucionales.</div>
        </div>
        
        <div class="features-grid">
            <div class="feature-card">
                <div class="feature-icon">⚙️</div>
                <div class="feature-title">Análisis Preciso</div>
                <div class="feature-desc">Evaluación estricta basada únicamente en los criterios de su rúbrica.</div>
            </div>
            <div class="feature-card">
                <div class="feature-icon">📊</div>
                <div class="feature-title">Datos Estructurados</div>
                <div class="feature-desc">Generación automática de métricas, notas y retroalimentación accionable.</div>
            </div>
            <div class="feature-card">
                <div class="feature-icon">📑</div>
                <div class="feature-title">Reportes Oficiales</div>
                <div class="feature-desc">Exportación instantánea a PDF y registro histórico en Excel/CSV.</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    col_form, col_results = st.columns([1.2, 1], gap="large")

    with col_form:
        st.markdown("<h3 style='margin-bottom: 1.5rem; font-weight: 600; color: #0F172A;'>Panel de Evaluación</h3>", unsafe_allow_html=True)
        
        profesor = st.text_input("Nombre del Evaluador", value="", key="prof_input")
        estudiante = st.text_input("Nombre del Estudiante", value="", key="est_input")

        st.markdown("<hr style='border: 0; height: 1px; background: #E2E8F0; margin: 1.5rem 0;'>", unsafe_allow_html=True)
        st.markdown("<p style='font-weight: 600; color: #1E293B; margin-bottom: 0.5rem;'>1. Rúbrica de Evaluación</p>", unsafe_allow_html=True)
        
        opcion_rubrica = st.radio("Formato de rúbrica", ["Texto directo", "Archivo (PDF/Imagen)"], horizontal=True, label_visibility="collapsed")
        rubrica_parts = []
        if opcion_rubrica == "Texto directo":
            rubrica_texto = st.text_area("Criterios de evaluación", height=120, label_visibility="collapsed")
            if rubrica_texto.strip():
                rubrica_parts.append(f"--- RÚBRICA ---\n{rubrica_texto}")
        else:
            rubrica_file = st.file_uploader("Documento de rúbrica", type=["pdf", "png", "jpg"], key="rubrica_file")
            if rubrica_file:
                rubrica_parts.append(types.Part.from_bytes(data=rubrica_file.read(), mime_type=rubrica_file.type))
                rubrica_parts.append("Este archivo es la rúbrica de evaluación.")

        st.markdown("<br><p style='font-weight: 600; color: #1E293B; margin-bottom: 0.5rem;'>2. Evidencia del Estudiante</p>", unsafe_allow_html=True)
        
        opcion_trabajo = st.radio("Formato de evidencia", ["Texto directo", "Archivo (PDF/Imagen)"], horizontal=True, label_visibility="collapsed")
        trabajo_parts = []
        if opcion_trabajo == "Texto directo":
            trabajo_texto = st.text_area("Contenido a evaluar", height=150, label_visibility="collapsed")
            if trabajo_texto.strip():
                trabajo_parts.append(f"--- TRABAJO ---\n{trabajo_texto}")
        else:
            trabajo_file = st.file_uploader("Trabajo del estudiante", type=["pdf", "png", "jpg"], key="trabajo_file")
            if trabajo_file:
                trabajo_parts.append(types.Part.from_bytes(data=trabajo_file.read(), mime_type=trabajo_file.type))
                trabajo_parts.append("Este archivo es el trabajo del estudiante.")

        st.markdown("<br>", unsafe_allow_html=True)
        btn_evaluar = st.button("Ejecutar Análisis Automatizado", use_container_width=True)

    with col_results:
        st.markdown("<h3 style='margin-bottom: 1.5rem; font-weight: 600; color: #0F172A;'>Resultados</h3>", unsafe_allow_html=True)
        
        if btn_evaluar:
            if not rubrica_parts or not trabajo_parts:
                st.error("Requisito: Ingrese la rúbrica y la evidencia del estudiante.")
                return

            client = get_gemini_client()
            prompt_sistema = """
Evalúa el trabajo del estudiante contrastándolo únicamente con la rúbrica.
Responde SIEMPRE con el siguiente formato exacto al inicio:
[PUNTAJE_OBTENIDO]: <valor numérico>
[NOTA_FINAL]: <nota final>

Luego, redacta un informe estructurado:
1. Resumen Ejecutivo.
2. Desglose por criterio.
3. Fortalezas.
4. Oportunidades de mejora.
Usa lenguaje técnico y objetivo.
            """.strip()

            with st.spinner("Procesando evaluación..."):
                resultado = generar_evaluacion_con_reintentos(client, rubrica_parts + trabajo_parts, prompt_sistema)

            if resultado:
                puntaje = extraer_metrica(r'\[PUNTAJE_OBTENIDO\]:\s*(.*)', resultado)
                nota = extraer_metrica(r'\[NOTA_FINAL\]:\s*(.*)', resultado)
                feedback_limpio = re.sub(r'\[(PUNTAJE_OBTENIDO|NOTA_FINAL)\]:.*', '', resultado).strip()

                st.session_state["eval_data"] = {
                    "docente": profesor, "estudiante": estudiante,
                    "puntaje": puntaje, "nota": nota, "feedback": feedback_limpio
                }

                df_actual = cargar_registro()
                nueva_fila = pd.DataFrame([{
                    "Docente": profesor or "N/A", "Estudiante": estudiante or "N/A",
                    "Puntaje": puntaje, "Nota": nota, "Fecha": datetime.now().strftime("%Y-%m-%d %H:%M")
                }])
                df_actual = pd.concat([df_actual, nueva_fila], ignore_index=True)
                guardar_registro(df_actual)

        if "eval_data" in st.session_state:
            data = st.session_state["eval_data"]
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"<div class='result-metric'><div class='result-value'>{data['puntaje']}</div><div class='result-label'>Puntaje</div></div>", unsafe_allow_html=True)
            with c2:
                st.markdown(f"<div class='result-metric'><div class='result-value'>{data['nota']}</div><div class='result-label'>Nota Final</div></div>", unsafe_allow_html=True)

            st.markdown(f"<div style='background: #F8FAFC; padding: 1.5rem; border-radius: 8px; border: 1px solid #E2E8F0; font-size: 0.95rem;'>{data['feedback'].replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

            pdf_bytes = generar_pdf_informe(data["docente"], data["estudiante"], data["nota"], data["puntaje"], data["feedback"])
            st.download_button(label="Descargar Informe Oficial PDF", data=pdf_bytes, file_name="informe_evaluacion.pdf", mime="application/pdf", use_container_width=True)
        else:
            st.markdown("<div style='text-align: center; color: #94A3B8; padding: 4rem 0;'>Esperando datos de evaluación...</div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()