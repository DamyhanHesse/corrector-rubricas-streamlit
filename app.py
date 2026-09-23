import streamlit as st
import json, io, os
import pandas as pd
from google import genai
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

st.set_page_config(page_title="Corrector Docente", layout="centered")

# Estilo directo sobre los componentes nativos de Streamlit
st.markdown("""
    <style>
    /* Fondo general gris muy claro como la maqueta móvil */
    .stApp {
        background-color: #F1F4F9 !important;
    }

    /* Ocultar elementos innecesarios */
    #MainMenu, header, footer {visibility: hidden;}

    /* Títulos limpios y de alto contraste */
    h1 {
        color: #1E293B !important;
        font-size: 26px !important;
        font-weight: 800 !important;
        letter-spacing: -0.5px;
        margin-bottom: 2px !important;
    }
    h2, h3 {
        color: #334155 !important;
        font-size: 17px !important;
        font-weight: 700 !important;
    }

    /* Textos y etiquetas siempre legibles en negro */
    label, p, span {
        color: #0F172A !important;
        font-size: 14px !important;
        font-weight: 600 !important;
    }

    /* Campos de entrada blancos con bordes sutiles */
    .stTextInput input, .stTextArea textarea {
        background-color: #FFFFFF !important;
        color: #0F172A !important;
        border: 1.5px solid #CBD5E1 !important;
        border-radius: 12px !important;
        font-size: 14px !important;
        font-weight: 500 !important;
    }

    /* Botón Violeta exacto al ejemplo (EVENT INFOS) */
    div.stButton > button:first-child {
        background-color: #6C5CE7 !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 12px !important;
        font-size: 15px !important;
        font-weight: 700 !important;
        padding: 0.65rem 1.4rem !important;
        box-shadow: 0 4px 14px rgba(108, 92, 231, 0.3) !important;
        width: 100% !important;
    }
    div.stButton > button:first-child:hover {
        background-color: #5A4AD1 !important;
    }

    /* Métrica de la nota */
    [data-testid="stMetricValue"] {
        color: #6C5CE7 !important;
        font-size: 38px !important;
        font-weight: 800 !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("spid. Corrector")
st.caption("Corrección con rúbricas y retroalimentación directa")

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

# Contenedor 1: Parámetros de evaluación
with st.container(border=True):
    st.subheader("Configuración de Evaluación")
    nombre_profesor = st.text_input("Nombre del Profesor/a", value="Profesor/a Evaluador/a")
    rubrica = st.text_area("Criterios de la Rúbrica", height=150, placeholder="Pega aquí los ítems y descriptores...")
    archivo = st.file_uploader("Prueba del alumno (PDF o Imagen)", type=["pdf", "png", "jpg", "jpeg"])
    boton_evaluar = st.button("Evaluar y Calificar")

# Contenedor 2: Resultados
if boton_evaluar:
    if not API_KEY:
        st.error("Falta configurar la clave GEMINI_API_KEY en los Secrets de Streamlit.")
    elif not rubrica or not archivo:
        st.warning("Completa la rúbrica y sube la prueba antes de evaluar.")
    else:
        with st.spinner("Analizando y calificando..."):
            try:
                client = genai.Client(api_key=API_KEY)
                prompt = f"""
                Evalúa la prueba adjunta según esta rúbrica:
                {rubrica}
                
                Devuelve ÚNICAMENTE un objeto JSON válido sin texto adicional ni bloques markdown:
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
                
                with st.container(border=True):
                    st.subheader("Resultado de Evaluación")
                    st.write(f"**Estudiante:** {data.get('nombre')}")
                    st.metric(label="Nota Final", value=data.get('nota'))
                    st.write(f"**Puntaje:** {data.get('puntaje')} pts")
                    st.write(f"**Retroalimentación:** {data.get('feedback')}")
                    
                    # Generación PDF
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
                
                guardar_en_registro(data, nombre_profesor)
                
            except Exception as e:
                st.error(f"Error durante el proceso: {e}")

# Contenedor 3: Planilla acumulada
with st.container(border=True):
    st.subheader("Planilla Consolidada de Evaluaciones")
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
        st.write("Aún no hay calificaciones registradas. Aparecerán aquí automáticamente al evaluar.")