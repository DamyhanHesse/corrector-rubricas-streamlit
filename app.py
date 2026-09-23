import streamlit as st
import json, io, os
import pandas as pd
from google import genai
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

st.set_page_config(page_title="Corrector con Rúbrica", layout="wide")

# Inyección de estilos directos con contraste asegurado
st.markdown("""
    <style>
    /* 1. Fondo general claro para máxima legibilidad */
    .stApp {
        background-color: #F8F9FA;
        color: #2A363B;
    }

    /* 2. Barra superior con Verde Salvia (#99B898) */
    .cabecera-paleta {
        background-color: #99B898;
        padding: 22px;
        border-radius: 12px;
        margin-bottom: 24px;
        border-bottom: 5px solid #FECEA8;
    }
    .cabecera-paleta h1 {
        color: #FFFFFF !important;
        font-size: 28px !important;
        font-weight: 800 !important;
        margin: 0 !important;
    }

    /* 3. Subtítulos con Melocotón (#FECEA8) y texto oscuro */
    .subtitulo-caja {
        background-color: #FECEA8;
        color: #2A363B !important;
        padding: 10px 16px;
        border-radius: 8px;
        font-size: 18px;
        font-weight: 700;
        margin-bottom: 16px;
        border-left: 6px solid #FF847C;
    }

    /* Etiquetas de campos siempre visibles */
    label, p, span {
        color: #2A363B !important;
        font-size: 15px !important;
        font-weight: 600 !important;
    }

    /* 4. Entradas con borde Coral Claro (#FF847C) */
    .stTextInput input, .stTextArea textarea {
        background-color: #FFFFFF !important;
        color: #2A363B !important;
        border: 2px solid #FF847C !important;
        border-radius: 8px !important;
        font-size: 15px !important;
    }

    /* 5. Botón de acción Coral Rojizo (#E84A5F) */
    div.stButton > button:first-child {
        background-color: #E84A5F !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 8px !important;
        font-size: 16px !important;
        font-weight: 700 !important;
        padding: 0.6rem 1.4rem !important;
        transition: 0.2s;
    }
    div.stButton > button:first-child:hover {
        background-color: #FF847C !important;
        color: #2A363B !important;
    }

    /* Nota numérica destacada */
    [data-testid="stMetricValue"] {
        color: #E84A5F !important;
        font-size: 40px !important;
        font-weight: 800 !important;
    }

    /* 6. Franja inferior Gris Petróleo (#2A363B) */
    .contenedor-planilla {
        background-color: #2A363B;
        padding: 24px;
        border-radius: 12px;
        margin-top: 30px;
    }
    .contenedor-planilla h3 {
        color: #FECEA8 !important;
        font-size: 20px !important;
        font-weight: 700 !important;
        margin-top: 0 !important;
    }
    .contenedor-planilla p {
        color: #FFFFFF !important;
    }
    </style>
""", unsafe_allow_html=True)

# Cabecera verde salvia
st.markdown("""
<div class="cabecera-paleta">
    <h1>Corrector y Retroalimentador de Pruebas</h1>
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

col1, col2 = st.columns(2)

with col1:
    st.markdown('<div class="subtitulo-caja">1. Entradas de Evaluación</div>', unsafe_allow_html=True)
    nombre_profesor = st.text_input("Nombre del Profesor/a", value="Profesor/a Evaluador/a")
    rubrica = st.text_area("Pega aquí la rúbrica de evaluación:", height=180)
    archivo = st.file_uploader("Sube la prueba del alumno (PDF o Imagen)", type=["pdf", "png", "jpg", "jpeg"])
    boton_evaluar = st.button("Evaluar y Calificar")

with col2:
    st.markdown('<div class="subtitulo-caja">2. Resultado del Alumno</div>', unsafe_allow_html=True)
    if boton_evaluar:
        if not API_KEY:
            st.error("Falta configurar la GEMINI_API_KEY en los Secrets de Streamlit.")
        elif not rubrica or not archivo:
            st.warning("Debes ingresar la rúbrica y subir la prueba del alumno.")
        else:
            with st.spinner("Evaluando documento..."):
                try:
                    client = genai.Client(api_key=API_KEY)
                    prompt = f"""
                    Evalúa la prueba adjunta según esta rúbrica:
                    {rubrica}
                    
                    Devuelve ÚNICAMENTE un objeto JSON válido con este formato exacto, sin bloques markdown ni texto extra:
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
                    
                    data = json.loads(res.text.replace("```json", "").replace("```", "").strip())
                    
                    st.success("Evaluación finalizada.")
                    st.write(f"**Estudiante:** {data.get('nombre')}")
                    st.metric(label="Nota Final", value=data.get('nota'))
                    st.write(f"**Puntaje:** {data.get('puntaje')} pts")
                    st.write(f"**Feedback:** {data.get('feedback')}")
                    
                    # Generación de PDF con metadatos
                    buffer = io.BytesIO()
                    titulo_pdf = f"Informe de Evaluación - {data.get('nombre', 'Estudiante')}"
                    
                    doc = SimpleDocTemplate(
                        buffer,
                        pagesize=letter,
                        title=titulo_pdf,
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
                    st.info("Datos agregados a la planilla consolidada.")
                    
                except Exception as e:
                    st.error(f"Error durante el proceso: {e}")

# Sección inferior gris petróleo
st.markdown('<div class="contenedor-planilla">', unsafe_allow_html=True)
st.markdown('<h3>Planilla Consolidada de Evaluaciones</h3>', unsafe_allow_html=True)

if os.path.exists(ARCHIVO_PLANILLA):
    try:
        df = pd.read_csv(ARCHIVO_PLANILLA, on_bad_lines='skip')
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
    except Exception:
        os.remove(ARCHIVO_PLANILLA)
        st.rerun()
else:
    st.markdown('<p>Aún no hay calificaciones registradas. Aparecerán aquí automáticamente al evaluar.</p>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)