import os
import time
import io
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
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS VISUALES PREMIUM (CSS)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="EduEvalua AI - Corrector Profesional",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Inyección de CSS para transformar la interfaz estándar de Streamlit
st.markdown("""
    <style>
    /* Fondo general y fuentes */
    @import url('https://googleapis.com');
    
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Inter', sans-serif;
        background-color: #0F172A; /* Fondo oscuro moderno (Slate 900) */
        color: #F8FAFC;
    }
    
    /* Encabezados */
    h1 {
        font-weight: 700 !important;
        color: #FFFFFF !important;
        letter-spacing: -0.02em;
    }
    h3 {
        font-weight: 600 !important;
        color: #38BDF8 !important; /* Celeste tecnológico */
        margin-bottom: 15px !important;
    }
    
    /* Contenedores y Tarjetas (Cards) */
    div[data-testid="stColumn"] {
        background-color: #1E293B; /* Fondo de tarjetas (Slate 800) */
        padding: 24px !important;
        border-radius: 16px !important;
        border: 1px solid #334155;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    
    /* Estilizar subidores de archivos (File Uploader) */
    div[data-testid="stFileUploader"] {
        background-color: #0F172A;
        border: 2px dashed #475569 !important;
        border-radius: 12px !important;
        padding: 10px;
    }
    
    /* Inputs de texto */
    input {
        background-color: #0F172A !important;
        color: #FFFFFF !important;
        border: 1px solid #475569 !important;
        border-radius: 8px !important;
    }
    
    /* Tarjetas de Métricas customizadas (Nota y Puntaje) */
    .metric-card {
        background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
        border: 1px solid #38BDF8;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 10px 15px -3px rgba(56, 189, 248, 0.1);
    }
    .metric-title {
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #94A3B8;
        margin-bottom: 5px;
    }
    .metric-value {
        font-size: 36px;
        font-weight: 700;
        color: #38BDF8;
    }
    
    /* Modificaciones de espaciados nativos de Streamlit */
    block-container {
        padding-top: 2rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

CSV_FILE = "registro_calificaciones.csv"

# -----------------------------------------------------------------------------
# 2. CLIENTE GEMINI Y BUCLE DE REINTENTOS ESCALONADOS
# -----------------------------------------------------------------------------
def get_gemini_client():
    api_key = st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        st.error("No se encontró 'GEMINI_API_KEY' en los Secrets de Streamlit.")
        st.stop()
    return genai.Client(api_key=api_key)

def generar_evaluacion_con_reintentos(client, contents, prompt_sistema, max_retries=3):
    model_id = "gemini-3.6-flash"
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
                else:
                    st.error("⚠️ Se ha alcanzado el límite de cuota temporal de la API.")
                    return None
            elif "503" in str(e):
                if intento < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    st.error("⚠️ El servicio está temporalmente saturado (503). Inténtalo más tarde.")
                    return None
            else:
                st.error(f"Error en la API de Google Gemini: {e}")
                return None
        except Exception as ex:
            st.error(f"Error inesperado: {ex}")
            return None
    return None

# -----------------------------------------------------------------------------
# 3. GESTIÓN DEL REGISTRO LOCAL CSV / EXCEL
# -----------------------------------------------------------------------------
def cargar_registro():
    if os.path.exists(CSV_FILE):
        try:
            return pd.read_csv(CSV_FILE, on_bad_lines='skip')
        except Exception:
            return pd.DataFrame(columns=["Docente", "Estudiante", "Puntaje", "Nota", "Fecha"])
    else:
        return pd.DataFrame(columns=["Docente", "Estudiante", "Puntaje", "Nota", "Fecha"])

def guardar_registro(df):
    df.to_csv(CSV_FILE, index=False)

def exportar_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Calificaciones')
    return output.getvalue()

# -----------------------------------------------------------------------------
# 4. GENERACIÓN DE INFORME PDF CON REPORTLAB
# -----------------------------------------------------------------------------
def generar_pdf_informe(nombre_docente, nombre_estudiante, nota, puntaje, feedback_texto):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40,
        title=f"Informe de Evaluación - {nombre_estudiante}",
        author=nombre_docente if nombre_docente else "Docente Evaluador"
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'], fontSize=18, leading=22, textColor=colors.HexColor('#1E293B'), spaceAfter=12
    )
    body_style = ParagraphStyle(
        'DocBody', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.HexColor('#334155'), spaceAfter=8
    )

    story = [Paragraph("Informe de Evaluación y Retroalimentación", title_style), Spacer(1, 10)]

    data = [
        [Paragraph("<b>Docente:</b>", body_style), Paragraph(nombre_docente if nombre_docente else "No especificado", body_style)],
        [Paragraph("<b>Estudiante:</b>", body_style), Paragraph(nombre_estudiante if nombre_estudiante else "No especificado", body_style)],
        [Paragraph("<b>Puntaje Obt.:</b>", body_style), Paragraph(str(puntaje), body_style)],
        [Paragraph("<b>Nota Final:</b>", body_style), Paragraph(str(nota), body_style)]
    ]
    
    t = Table(data, colWidths=[100, 400])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    
    story.append(t)
    story.append(Spacer(1, 15))
    story.append(Paragraph("<b>Detalle de Retroalimentación Formativa:</b>", body_style))
    story.append(Spacer(1, 5))
    
    for linea in feedback_texto.split('\n'):
        if linea.strip():
            story.append(Paragraph(linea.replace('<', '&lt;').replace('>', '&gt;'), body_style))
        else:
            story.append(Spacer(1, 4))
            
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# -----------------------------------------------------------------------------
# 5. INTERFAZ DE USUARIO (UX/UI REDEFINIDA)
# -----------------------------------------------------------------------------
def main():
    # Encabezado Premium estilizado con HTML
    st.markdown("""
        <div style='text-align: center; padding-bottom: 25px;'>
            <h1 style='margin-bottom: 0px;'>✨ EduEvalua AI</h1>
            <p style='color: #94A3B8; font-size: 16px; margin-top: 5px;'>Sistemas Avanzados de Retroalimentación Docente con Inteligencia Artificial</p>
        </div>
    """, unsafe_allow_html=True)

    col_izq, col_der = st.columns([1, 1], gap="large")

    with col_izq:
        st.subheader("🛠️ Configuración y Entradas")
        
        profesor = st.text_input("Nombre del Profesor/a", placeholder="Ej. Carlos Mendoza")
        estudiante = st.text_input("Nombre del Estudiante", placeholder="Ej. Francisca Silva")

        st.markdown("<br><p style='font-weight:600; color:#94A3B8; margin-bottom:5px;'>Rúbrica de Evaluación</p>", unsafe_allow_html=True)
        opcion_rubrica = st.radio("Seleccione formato", ["Texto directo", "Archivo (Imagen/PDF)"], horizontal=True, label_visibility="collapsed")
        
        rubrica_content = None
                st.markdown("<br><p style='font-weight:600; color:#94A3B8; margin-bottom:5px;'>Rúbrica de Evaluación</p>", unsafe_allow_html=True)
        opcion_rubrica = st.radio("Seleccione formato", ["Texto directo", "Archivo (Imagen/PDF)"], horizontal=True, label_visibility="collapsed")
        
        rubrica_content = None
        if opcion_rubrica == "Texto directo":
            rubrica_content = st.text_area("Pegue la rúbrica detallada aquí", height=120, placeholder="Escriba los criterios o pegue la tabla de evaluación...")
        else:
            rubrica_file = st.file_uploader("Subir Rúbrica", type=["pdf", "png", "jpg", "jpeg"], key="rubrica_file")
            if rubrica_file:
                # Asegúrate de que esta línea de abajo tenga la sangría correcta hacia la derecha
                rubrica_content = types.Part.from_bytes(data=rubrica_file.read(), mime_type=rubrica_file.type)
