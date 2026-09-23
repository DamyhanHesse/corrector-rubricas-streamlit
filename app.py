import streamlit as st
import json, io, os
import pandas as pd
from google import genai
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

st.set_page_config(page_title="Corrector Docente", layout="centered")

# Estilo visual App Mobile / Clean Light
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"], .stApp {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        background-color: #F4F6F9 !important;
        color: #0F172A !important;
    }

    /* Encabezado principal */
    .app-header {
        background: linear-gradient(135deg, #1E1B4B 0%, #312E81 50%, #4338CA 100%);
        padding: 28px 24px;
        border-radius: 20px;
        color: #FFFFFF;
        margin-bottom: 24px;
        box-shadow: 0 10px 25px -5px rgba(49, 46, 129, 0.25);
    }
    .app-header h1 {
        color: #FFFFFF !important;
        font-size: 26px !important;
        font-weight: 800 !important;
        margin: 0 0 6px 0 !important;
    }
    .app-header p {
        color: #C7D2FE !important;
        font-size: 14px !important;
        margin: 0 !important;
        font-weight: 500 !important;
    }

    /* Tarjetas tipo App */
    .card {
        background: #FFFFFF;
        padding: 22px;
        border-radius: 18px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04);
        margin-bottom: 20px;
    }
    .card-title {
        font-size: 16px;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 14px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* Textos y etiquetas legibles */
    label, p, span, .stMarkdown {
        color: #1E293B !important;
        font-size: 14px !important;
        font-weight: 600 !important;
    }

    /* Campos de entrada nítidos */
    .stTextInput input, .stTextArea textarea {
        background-color: #F8FAFC !important;
        color: #0F172A !important;
        border: 1.5px solid #CBD5E1 !important;
        border-radius: 12px !important;
        font-size: 14px !important;
        font-weight: 500 !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
        border-color: #6366F1 !important;
        box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15) !important;
    }

    /* Botón morado / violeta */
    div.stButton > button:first-child {
        background: linear-gradient(135deg, #6366F1 0%, #4F46E5 100%) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 14px !important;
        font-size: 15px !important;
        font-weight: 700 !important;
        padding: 0.75rem 1.5rem !important;
        box-shadow: 0 4px 14px rgba(79, 70, 229, 0.35) !important;
        width: 100% !important;
    }
    div.stButton > button:first-child:hover {
        background: linear-gradient(135deg, #4F46E5 0%, #4338CA 100%) !important;
        box-shadow: 0 6px 18px rgba(79, 70, 229, 0.45) !important;
    }

    /* Métrica de Nota destacada */
    [data-testid="stMetricValue"] {
        color: #4F46E5 !important;
        font-size: 38px !important;
        font-weight: 800 !important;
    }

    /* Botón de descarga */
    .stDownloadButton > button {
        background-color: #0F172A !important;
        color: #FFFFFF !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
        border: none !important;
        width: 100% !important;
    }
    </style>
""", unsafe_allow_html=True)

# Cabecera superior moderna
st.markdown("""
<div class="app-header">
    <h1>Evaluador de Rúbricas</h1>
    <p>Corrección automatizada y retroalimentación directa</p>
</div>
""", unsafe_allow_html=True)

API_KEY = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY"))
ARCHIVO_PLANILLA = "registro_calificaciones.csv"

def guardar_en_registro(datos, profesor):
    fila = pd.DataFrame([{
        "Docente": profesor,
        "Estudiante": datos.get("nombre", "No especificado"),
        "RUT": datos.get("rut", "No especificado"),
        "Puntaje": datos.get("puntaje", 0.0),
        "Nota Final": datos.get("nota", 0.0),
        "Feedback": str(datos.get("feedback", "")).replace("\n", " ")
    }])
    if not os.path.exists(ARCHIVO_PLANILLA):
        fila.to_csv(ARCHIVO_PLANILLA, index=False, encoding="utf-8-sig")
    else:
        fila.to_csv(ARCHIVO_PLANILLA, mode="a", header=False, index=False, encoding="utf-8-sig")

# Tarjeta 1: Parámetros
st.markdown('<div class="card"><div class="card-title">Configuración de Evaluación</div>', unsafe_allow_html=True)
nombre_profesor = st.text_input("Nombre del Profesor/a", value="Profesor/a Evaluador/a")
rubrica = st.text_area("Criterios de la Rúbrica", height=150, placeholder="Pega aquí los ítems, puntajes o niveles...")
archivo = st.file_uploader("Prueba del estudiante (PDF o Imagen)", type=["pdf", "png", "jpg", "jpeg"])
boton_evaluar = st.button("Evaluar y Calificar")
st.markdown('</div>', unsafe_allow_html=True)

# Tarjeta 2: Resultados
if boton_evaluar:
    if not API_KEY:
        st.error("Falta configurar la clave GEMINI_API_KEY en los Secrets de la app.")
    elif not rubrica or not archivo:
        st.warning("Por favor completa la rúbrica y sube la prueba antes de evaluar.")
    else:
        with st.spinner("Procesando y analizando evaluación..."):
            try:
                client = genai.Client(api_key=API_KEY)
                prompt = f"""
                Evalúa la prueba adjunta con la siguiente rúbrica:
                {rubrica}
                
                Devuelve EXCLUSIVAMENTE un objeto JSON válido sin formato markdown ni texto extra:
                {{
                    "nombre": "Nombre del alumno",
                    "rut": "RUT del alumno",
                    "puntaje": 20.0,
                    "nota": 7.0,
                    "feedback": "Retroalimentación formativa y clara"
                }}
                """
                
                res = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[genai.types.Part.from_bytes(data=archivo.read(), mime_type=archivo.type), prompt]
                )
                
                limpio = res.text.replace("```json", "").replace("```", "").strip()
                data = json.loads(limpio)
                
                st.markdown('<div class="card"><div class="card-title">Resultado de Evaluación</div>', unsafe_allow_html=True)
                st.write(f"**Estudiante:** {data.get('nombre')}")
                st.metric(label="Nota Final", value=data.get('nota'))
                st.write(f"**Puntaje:** {data.get('puntaje')} pts")
                st.write(f"**Retroalimentación:** {data.get('feedback')}")
                
                # PDF
                buffer = io.BytesIO()
                doc = SimpleDocTemplate(
                    buffer,
                    pagesize=letter,
                    title=f"Informe - {data.get('nombre', 'Estudiante')}",
                    author=nombre_profesor
                )
                styles = getSampleStyleSheet()
                historia = [
                    Paragraph(f"<b>Informe: {data.get('nombre')}</b>", styles['Title']),
                    Spacer(1, 10),
                    Paragraph(f"<b>Profesor/a:</b> {nombre_profesor}", styles['Normal']),
                    Spacer(1, 10),
                    Paragraph(f"<b>RUT:</b> {data.get('rut')} | <b>Puntaje:</b> {data.get('puntaje')} | <b>Nota:</b> {data.get('nota')}", styles['Normal']),
                    Spacer(1, 10),
                    Paragraph(f"<b>Feedback:</b> {data.get('feedback')}", styles['Normal'])
                ]
                doc.build(historia)
                buffer.seek(0)
                
                st.download_button(
                    label="📄 Descargar Informe en PDF",
                    data=buffer,
                    file_name=f"informe_{data.get('nombre', 'alumno')}.pdf",
                    mime="application/pdf"
                )
                st.markdown('</div>', unsafe_allow_html=True)
                
                guardar_en_registro(data, nombre_profesor)
                
            except Exception as e:
                st.error(f"Ocurrió un error al procesar la evaluación: {e}")

# Tarjeta 3: Planilla acumulada
st.markdown('<div class="card"><div class="card-title">Planilla de Evaluaciones Acumuladas</div>', unsafe_allow_html=True)

if os.path.exists(ARCHIVO_PLANILLA):
    try:
        df = pd.read_csv(ARCHIVO_PLANILLA, on_bad_lines='skip')
        st.dataframe(df, use_container_width=True)
        
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                label="📥 Descargar Planilla CSV",
                data=df.to_csv(index=False, encoding="utf-8-sig"),
                file_name="calificaciones_curso.csv",
                mime="text/csv"
            )
        with c2:
            if st.button("Limpiar Registro"):
                os.remove(ARCHIVO_PLANILLA)
                st.rerun()
    except Exception:
        os.remove(ARCHIVO_PLANILLA)
        st.rerun()
else:
    st.write("Aún no se han registrado notas. Aparecerán aquí tras cada corrección.")

st.markdown('</div>', unsafe_allow_html=True)