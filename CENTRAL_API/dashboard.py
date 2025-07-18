import os
import streamlit as st
import requests
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="🚦 Toll Record Monitor", layout="wide")
st.title("🚦 Toll Record Monitor")

# 🔄 Auto refresh every 5 seconds
st_autorefresh(interval=5000, limit=None, key="refresh")

API_URL = "http://localhost:8000/ver-registros"
# USER DATE TO ACESS
USUARIO = "admin"
CLAVE = "1234"

# Session state
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

# Log in forms
if not st.session_state.autenticado:
    st.title("🔐 Login")
    usuario = st.text_input("User")
    clave = st.text_input("Password", type="password")
    if st.button("Log in"):
        if usuario == USUARIO and clave == CLAVE:
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("❌ Wrong user or password")
    st.stop()

status_icons = {
    "⏳ Waiting for more data": "⏳",
    "✅ Valid: Allowed discount": "✅",
    "❌ Motorcycle with no helment": "⚠️",
    "🚨 No helmet and PLATE/RFID dont match": "🚨",
}

vehiculo_icons = {
    "car": "🚗",
    "motorcycle": "🏍️"
}

try:
    res = requests.get(API_URL).json()
    st.write(f"Total of events: {len(res)}")

    for event_id, datos in res.items():
        st.markdown(f"### 🆔 Event: `{event_id}`")

        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            tipo = datos.get('vehiculo', 'unknown')
            st.write(f"**Vehicle:** {vehiculo_icons.get(tipo, '❓')} {tipo}")

        with col2:
            st.write(f"**📷 Plate:** {datos.get('chapa') or '⏳'}")

        with col3:
            st.write(f"**🛰️ RFID:** {datos.get('rfid') or '⏳'}")

        with col4:
            tipo = datos.get('vehiculo', 'unknown')
            if tipo == "motorcycle":
                casco = datos.get("casco")
                if casco is None:
                    st.write("**🪖 helmet:** ⏳")
                else:
                    st.write(f"**🪖 Helmet:** {'✅' if casco else '❌'}")
            else:
                st.write("")  # For cars, not show


        with col5:
            accion = datos.get("accion", "⏳ Waiting for more data")
            st.write(f"**📣 Action:** {status_icons.get(accion, '')} {accion}")

        img1 = datos.get("img_path")
        img2 = datos.get("foto_casco_path")


        img_cols = st.columns(2)
        if img1 and os.path.exists(img1):
            img_cols[0].image(img1, caption="📸 Picture of plate", width=300)
        if img2 and os.path.exists(img2):
            img_cols[1].image(img2, caption="🪖 Picture of driver", width=300)

        st.markdown("---")

except Exception as e:
    st.error(f"❌ Error al conectar con la API: {e}")
