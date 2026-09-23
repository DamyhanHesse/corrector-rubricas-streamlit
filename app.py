import streamlit as st
import json, io, os, time
import pandas as pd
from google import genai
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

st.set_page_config(page_title="Corrector y Retroalimentador de Pruebas", layout="wide")
st.title("Corrector y Retroalimentador de Pruebas")

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
    st.subheader("1. Entradas de Evaluación")
    nombre_profesor = st.text_input("Nombre del Profesor/a", value="Profesor/a Evaluador/a")
    
    # Opción dual: subir archivo de rúbrica O escribirla
    archivo_rubrica = st.file_uploader("Sube la rúbrica (Imagen o PDF)", type=["pdf", "png", "jpg", "jpeg"], key="rubrica_file")
    rubrica_texto = st.text_area("O pega el texto de la rúbrica aquí:", height=100)
    
    archivo_prueba = st.file_uploader("Sube la prueba del alumno (PDF o Imagen)", type=["pdf", "png", "jpg", "jpeg"], key="prueba_file")
    boton_evaluar = st.button("Evaluar y Calificar", type="primary")

with col2:
    st.subheader("2. Resultado del Alumno")
    if boton_evaluar:
        if not API_KEY:
            st.error("Falta configurar la clave GEMINI_API_KEY en los Secrets de Streamlit.")
        elif not archivo_rubrica and not rubrica_texto.strip():
            st.warning("Debes subir el archivo de la rúbrica o pegar su texto.")
        elif not archivo_prueba:
            st.warning("Debes subir la prueba del alumno.")
        else:
            with st.spinner("Evaluando documento con la rúbrica..."):
                try:
                    client = genai.Client(api_key=API_KEY)
                    
                    # Preparar contenidos para la IA
                    prompt_instruccion = """
                    Evalúa la prueba adjunta utilizando la rúbrica proporcionada.
                    
                    Devuelve ÚNICAMENTE un objeto JSON válido con este formato exacto, sin bloques markdown ni texto extra:
                    {
                        "nombre": "Nombre del alumno",
                        "rut": "RUT del alumno",
                        "puntaje": 20.0,
                        "nota": 7.0,
                        "feedback": "Retroalimentación formativa y clara"
                    }
                    """
                    
                    partes_mensaje = []
                    
                    # Adjuntar rúbrica (sea archivo o texto)
                    if archivo_rubrica:
                        partes_mensaje.append(genai.types.Part.from_bytes(data=archivo_rubrica.read(), mime_type=archivo_rubrica.type))
                        partes_mensaje.append("La imagen/documento anterior corresponde a la RÚBRICA de evaluación.")
                    if rubrica_texto.strip():
                        partes_mensaje.append(f"Criterios de rúbrica en texto:\n{rubrica_texto}")
                        
                    # Adjuntar prueba del alumno
                    partes_mensaje.append(genai.types.Part.from_bytes(data=archivo_prueba.read(), mime_type=archivo_prueba.type))
                    partes_mensaje.append("El documento anterior corresponde a la PRUEBA del alumno a evaluar.")
                    partes_mensaje.append(prompt_instruccion)

                    modelos_respaldo = ["gemini-2.5-flash", "gemini-3.6-flash"]
                    res = None
                    ultimo_error = None

                    for modelo in modelos_respaldo:
                        try:
                            res = client.models.generate_content(
                                model=modelo,
                                contents=partes_mensaje
                            )
                            break
                        except Exception as err:
                            ultimo_error = err
                            time.sleep(1)
                            continue

                    if res is None:
                        raise ultimo_error

                    limpio = res.text.replace("```json", "").replace("```", "").strip()
                    data = json.loads(limpio)
                    
                    st.success("Evaluación finalizada.")
                    st.write(f"**Estudiante:** {data.get('nombre')}")
                    st.metric(label="Nota Final", value=data.get('nota'))
                    st.write(f"**Puntaje:** {data.get('puntaje')} pts")
                    st.write(f"**Feedback:** {data.get('feedback')}")
                    
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
                        label="Descargar Informe en PDF",
                        data=buffer,
                        file_name=f"informe_{data.get('nombre', 'alumno')}.pdf",
                        mime="application/pdf"
                    )
                    
                    guardar_en_registro(data, nombre_profesor)
                    st.info("Datos agregados a la planilla consolidada.")
                    
                except Exception as e:
                    st.error(f"Error durante el proceso: {e}")

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
        os.remove(ARCHIVO_PLANILLA)
        st.rerun()
else:
    st.write("Aún no hay calificaciones registradas. Aparecerán aquí automáticamente al evaluar.")