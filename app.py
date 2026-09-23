import streamlit as st
import json, io, os
import pandas as pd
from google import genai
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

st.set_page_config(page_title="Corrector con Rúbrica", layout="wide")

# Estilos en cascada de arriba a abajo según la paleta
st.markdown("""
    <style>
    /* 1. Fondo superior y cuerpo principal (#99B898) */
    .stApp {
        background: linear-gradient(180deg, #99B898 0%, #FECEA8 35%, #FFFFFF 100%);
        color: #2A363B;
    }

    /* Encabezado superior */
    h1 {
        color: #2A363B !important;
        font-weight: 800;
        text-shadow: 0 1px 2px rgba(255,255,255,0.4);
    }
    
    /* 2. Subtítulos y etiquetas intermedias (#FECEA8 y acento) */
    h2, h3 {
        color: #2A363B !important;
        font-weight: 700;
    }
    label, p, span {
        color: #2A363B !important;
        font-weight: 500;
    }

    /* Campos de entrada con fondo melocotón muy suave y borde #FF847C */
    .stTextInput input, .stTextArea textarea {
        background-color: #FFF6EE !important;
        color: #2A363B !important;
        border: 2px solid #FF847C !important;
        border-radius: 8px !important;
    }

    /* 3. Botón de acción principal (#E84A5F) con hover coral (#FF847C) */
    div.stButton > button:first-child {
        background-color: #E84A5F !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 8px !important;
        font-size: 16px !important;
        font-weight: bold !important;
        padding: 0.6rem 1.2rem !important;
        transition: 0.2s ease-in-out;
    }
    div.stButton > button:first-child:hover {
        background-color: #FF847C !important;
        color: #2A363B !important;
    }

    /* Indicador de Nota */
    [data-testid="stMetricValue"] {
        color: #E84A5F !important;
    }

    /* 4. Sección inferior (#2A363B) para la planilla */
    .seccion-inferior {
        background-color: #2A363B;
        padding: 24px;
        border-radius: 12px;
        margin-top: 25px;
    }
    .seccion-inferior h3 {
        color: #FECEA8 !important;
    }
    .seccion-inferior p {
        color: #FFFFFF !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("Corrector y Retroalimentador de Pruebas")

ARCHIVO_PLANILLA = "registro_calificaciones.csv"

def guardar_en_registro(datos):
    fila = pd.DataFrame([{
        "Estudiante": datos.get("nombre", "No especificado"),
        "RUT": datos.get("rut", "No especificado"),
        "Puntaje": datos.get("puntaje", 0.0),
        "Nota Final": datos.get("nota", 0.0),
        "Feedback": datos.get("feedback", "")
    }])
    if not os.path.exists(ARCHIVO_PLANILLA):
        fila.to_csv(ARCHIVO_PLANILLA, index=False, encoding="utf-8-sig")
    else:
        fila.to_csv(ARCHIVO_PLANILLA, mode="a", header=False, index=False, encoding="utf-8-sig")

col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Entradas de Evaluación")
    api_key = st.text_input("Gemini API Key (Google AI Studio)", type="password")
    rubrica = st.text_area("Pega aquí la rúbrica de evaluación:", height=180)
    archivo = st.file_uploader("Sube la prueba del alumno (PDF o Imagen)", type=["pdf", "png", "jpg", "jpeg"])
    boton_evaluar = st.button("Evaluar y Calificar")

with col2:
    st.subheader("2. Resultado del Alumno")
    if boton_evaluar:
        if not api_key or not rubrica or not archivo:
            st.warning("Debes ingresar la API Key, la rúbrica y el archivo del alumno.")
        else:
            with st.spinner("Evaluando documento..."):
                try:
                    client = genai.Client(api_key=api_key)
                    prompt = f"""
                    Evalúa la prueba adjunta según esta rúbrica:
                    {rubrica}
                    
                    Devuelve ÚNICAMENTE un objeto JSON válido con este formato exacto, sin bloques markdown ni texto extra:
                    {{
                        "nombre": "Nombre del alumno",
                        "rut": "RUT del alumno",
                        "puntaje": 20.0,
                        "nota": 7.0,
                        "feedback": "Retroalimentación clara, directa y formativa"
                    }}
                    """
                    
                    res = client.models.generate_content(
                        model="gemini-3.6-flash",
                        contents=[genai.types.Part.from_bytes(data=archivo.read(), mime_type=archivo.type), prompt]
                    )
                    
                    data = json.loads(res.text.replace("```json", "").replace("```", "").strip())
                    
                    st.success("Evaluación finalizada.")
                    st.write(f"**Estudiante:** {data.get('nombre')}")
                    st.metric(label="Nota Final", value=data.get('nota'))
                    st.write(f"**Feedback:** {data.get('feedback')}")
                    
                    buffer = io.BytesIO()
                    doc = SimpleDocTemplate(buffer, pagesize=letter)
                    styles = getSampleStyleSheet()
                    historia = [
                        Paragraph(f"<b>Informe: {data.get('nombre')}</b>", styles['Title']),
                        Spacer(1, 10),
                        Paragraph(f"<b>RUT:</b> {data.get('rut')} | <b>Puntaje:</b> {data.get('puntaje')} | <b>Nota:</b> {data.get('nota')}", styles['Normal']),
                        Spacer(1, 10),
                        Paragraph(f"<b>Feedback:</b> {data.get('feedback')}", styles['Normal'])
                    ]
                    doc.build(historia)
                    buffer.seek(0)
                    
                    st.download_button(
                        label="Descargar Informe en PDF",
                        data=buffer,
                        file_name=f"informe_{data.get('nombre', 'alumno')}.pdf",
                        mime="application/pdf"
                    )
                    
                    guardar_en_registro(data)
                    st.info("Datos agregados a la planilla consolidada.")
                    
                except Exception as e:
                    st.error(f"Error durante el proceso: {e}")

# Bloque inferior oscuro (#2A363B)
st.markdown('<div class="seccion-inferior">', unsafe_allow_html=True)
st.subheader("Planilla Consolidada de Evaluaciones")

if os.path.exists(ARCHIVO_PLANILLA):
    df = pd.read_csv(ARCHIVO_PLANILLA)
    st.dataframe(df, use_container_width=True)
    
    col_d1, col_d2 = st.columns([1, 1])
    with col_d1:
        st.download_button(
            label="📥 Descargar Planilla para Excel (.csv)",
            data=df.to_csv(index=False, encoding="utf-8-sig"),
            file_name="calificaciones_curso.csv",
            mime="text/csv"
        )
    with col_d2:
        if st.button("Limpiar registro (empezar curso nuevo)"):
            os.remove(ARCHIVO_PLANILLA)
            st.rerun()
else:
    st.write("Aún no hay calificaciones registradas. Aparecerán aquí automáticamente al evaluar.")

st.markdown('</div>', unsafe_allow_html=True)