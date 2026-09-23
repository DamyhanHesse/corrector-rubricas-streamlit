import streamlit as st
import json, io, os
import pandas as pd
from google import genai
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

st.set_page_config(page_title="Corrector y Retroalimentador de Pruebas", layout="wide")
st.title("Corrector y Retroalimentador de Pruebas")

# Obtener API Key desde los secretos del servidor o variable de entorno
API_KEY = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY"))

ARCHIVO_PLANILLA = "registro_calificaciones.csv"

def guardar_en_registro(datos, profesor):
    fila = pd.DataFrame([{
        "Docente": profesor,
        "Estudiante": datos.get("nombre", "No especificado"),
        "RUT": datos.get("rut", "No especificado"),
        "Puntaje": datos.get("puntaje", 0.0),
        "Nota Final": datos.get("nota", 0.0),
        "Feedback": datos.get("feedback", "").replace("\n", " ")
    }])
    if not os.path.exists(ARCHIVO_PLANILLA):
        fila.to_csv(ARCHIVO_PLANILLA, index=False, encoding="utf-8-sig")
    else:
        fila.to_csv(ARCHIVO_PLANILLA, mode="a", header=False, index=False, encoding="utf-8-sig")

col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Entradas de Evaluación")
    nombre_profesor = st.text_input("Nombre del Profesor/a", value="Profesor/a Evaluador/a")
    rubrica = st.text_area("Pega aquí la rúbrica de evaluación:", height=180)
    archivo = st.file_uploader("Sube la prueba del alumno (PDF o Imagen)", type=["pdf", "png", "jpg", "jpeg"])
    boton_evaluar = st.button("Evaluar y Calificar", type="primary")

with col2:
    st.subheader("2. Resultado del Alumno")
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
                        label="Descargar Informe en PDF",
                        data=buffer,
                        file_name=f"informe_{data.get('nombre', 'alumno')}.pdf",
                        mime="application/pdf"
                    )
                    
                    guardar_en_registro(data, nombre_profesor)
                    st.info("Datos agregados a la planilla consolidada.")
                    
                except Exception as e:
                    st.error(f"Error durante el proceso: {e}")

# --- PLANILLA CONSOLIDADA ---
st.divider()
st.subheader("Planilla Consolidada de Evaluaciones")

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
        # Si el CSV antiguo quedó dañado o incompatible, se elimina y se reinicia
        os.remove(ARCHIVO_PLANILLA)
        st.info("Se reinició el registro de notas para actualizar la estructura.")
        st.rerun()
else:
    st.write("Aún no hay calificaciones registradas. Aparecerán aquí automáticamente al evaluar.")