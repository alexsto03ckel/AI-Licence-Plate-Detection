from fastapi import FastAPI, UploadFile, File, Form
import shutil
import os
import requests
from fastapi import Header, HTTPException, Depends
import json
import time

from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from bson.binary import Binary


uri = "mongodb+srv://jossu5273:1234@f11215112-edward.lk2si.mongodb.net/?retryWrites=true&w=majority&appName=F11215112-Edward"

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi('1'))

# === Connect to DB and collection ===
db = client["TollSystem"]
collection = db["Incident"]
# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)

app = FastAPI()

def store_incident(image_path, incident_text):
    print("📁 Received path:", image_path)
    print("✅ os.path.exists:", os.path.exists(image_path))

    if not os.path.exists(image_path):
        print("❌ Image path not found.")
        return

    with open(image_path, "rb") as f:
        image_data = Binary(f.read())  # Convert to BSON binary format

    incident_doc = {
        "incident": incident_text,
        "image": image_data
    }

    result = collection.insert_one(incident_doc)
    print(f"✅ Incident stored with ID: {result.inserted_id}")


def cargar_apikeys():
    with open("apikeys.json", "r") as f:
        return json.load(f)

def verificar_apikey(x_api_key: str = Header(default=None)):
    apikeys = cargar_apikeys()
    for item in apikeys:
        if item["key"] == x_api_key:
            if item["activo"]:
                return item
            else:
                raise HTTPException(status_code=403, detail="🔒 API Key desactivada")
    raise HTTPException(status_code=403, detail="🚫 API Key inválida")

registros = {}
UPLOAD_DIR = "imagenes"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def crear_si_no_existe(event_id: str, vehicle: str = None):
    if event_id not in registros:
        registros[event_id] = {
            "chapa": None,
            "rfid": None,
            "casco": None,
            "vehiculo": vehicle,
            "accion": "⏳ Esperando más datos",
            "img_path": None,
            "foto_casco_path": None,
            "reporte_manual": None,
            "timestamp": time.time()  
        }

@app.post("/enviar-dato")
async def recibir_dato(
    event_id: str = Form(...),
    numero_chapa: str = Form(...),
    vehicle: str = Form(...),
    foto: UploadFile = File(...),
    apikey: str = Depends(verificar_apikey)
):
    crear_si_no_existe(event_id, vehicle)

    image_path = os.path.join(UPLOAD_DIR, f"{event_id}.jpg")
    with open(image_path, "wb") as f:
        shutil.copyfileobj(foto.file, f)

    registros[event_id]["chapa"] = numero_chapa
    registros[event_id]["img_path"] = image_path
    registros[event_id]["vehiculo"] = vehicle

    return {"status": "✅ Plate and pic recived ", "event_id": event_id}

@app.post("/enviar-rfid")
def recibir_rfid(
    event_id: str = Form(...),
    rfid: str = Form(...),
    apikey: str = Depends(verificar_apikey)
):
    crear_si_no_existe(event_id)

    registros[event_id]["rfid"] = rfid

    vehiculo = registros[event_id].get("vehiculo")
    casco = registros[event_id].get("casco")

    # ✅ Solo procesar si es auto o ya llegó casco
    if vehiculo != "moto" or casco is not None:
        return procesar_evento(event_id)
    
    # ❌ Si es moto pero aún no llegó casco, no procesar todavía
    registros[event_id]["accion"] = "⏳ waiting for more data"
    return {
        "status": "📥 RFID got, waiting Helmet",
        "accion": registros[event_id]["accion"],
        "registro_actual": registros[event_id]
    }

@app.post("/enviar-casco")
async def recibir_casco(
    event_id: str = Form(...),
    casco: bool = Form(...),
    foto_casco: UploadFile = File(None),
    apikey: str = Depends(verificar_apikey)
):
    crear_si_no_existe(event_id)

    registros[event_id]["casco"] = casco

    if foto_casco:
        casco_path = os.path.join(UPLOAD_DIR, f"{event_id}_casco.jpg")
        with open(casco_path, "wb") as f:
            shutil.copyfileobj(foto_casco.file, f)
        registros[event_id]["foto_casco_path"] = casco_path

    return procesar_evento(event_id)

def procesar_evento(event_id: str):
    registro = registros[event_id]
    permitir_descuento = False

    vehiculo = registro.get("vehiculo")
    if vehiculo is None:
        registro["accion"] = "⏳ Waiting for more data (vehicle)"
        return {
            "status": "📥 Actualized data",
            "permitir_descuento": False,
            "accion": registro["accion"],
            "registro_actual": registro
        }

    es_moto = vehiculo == "moto"


    # Solo para autos, se asume casco=True si no llegó
    if not es_moto and registro["casco"] is None:
        registro["casco"] = True

    # 🔒 NUEVO: no procesar si es moto y aún no llegó casco
    if es_moto and registro["casco"] is None:
        registro["accion"] = "⏳ Waiting for more data (helmet)"
        return {
            "status": "📥 Data updated",
            "permitir_descuento": False,
            "accion": registro["accion"],
            "registro_actual": registro
        }

    # Check que tenga chapa y rfid
    datos_completos = registro["chapa"] and registro["rfid"]

    if datos_completos:
        tiene_casco = registro["casco"]
        sin_casco = not tiene_casco
        chapa_mal = registro["chapa"] != registro["rfid"]

        if sin_casco or chapa_mal:
            if sin_casco and chapa_mal:
                registro["accion"] = "🚨 No helment and PLATE/RFID dont match"
                razon = "sin_casco_y_chapa_mal"
            elif sin_casco:
                registro["accion"] = "⚠️ Motorcycle with no helment"
                razon = "sin_casco"
                permitir_descuento = True
            else:
                registro["accion"] = "❌ Plate and RFID dont match"
                razon = "chapa_mal"

            try:
                img_file = open(registro["img_path"], "rb")
                files = {"foto": img_file}
                casco_file = None
                if "foto_casco_path" in registro and registro["foto_casco_path"]:
                    casco_file = open(registro["foto_casco_path"], "rb")
                    files["foto_casco"] = casco_file

                payload = {
                    "event_id": event_id,
                    "chapa_detectada": registro["chapa"],
                    "chapa_rfid": registro["rfid"],
                    "casco": tiene_casco,  # helmet_notified = True if casco=False
                    "razon": razon
                }
                store_incident(registro["img_path"], razon)
                print("🔍 Registro actual:", registro)
                print("📤 Enviando a Flask con payload:", payload)
                res = requests.post("http://140.118.209.162:5050/recibir-imagen", data=payload, files=files)
                print("📥 Respuesta:", res.status_code, res.text)
                registro["reporte_manual"] = res.json()
            except Exception as e:
                registro["reporte_manual"] = {"error": str(e)}
            finally:
                img_file.close()
                if casco_file:
                    casco_file.close()
        else:
            registro["accion"] = "✅ Valid: Allowed discount"
            permitir_descuento = True
    else:
        registro["accion"] = "⏳ Waiting for more data (Plate or RFID)"

    return {
        "status": "📥 Datos actualizados",
        "permitir_descuento": permitir_descuento,
        "accion": registro["accion"],
        "registro_actual": registro
    }

@app.get("/verificar-expirados")
def verificar_eventos_expirados():
    ahora = time.time()
    expirados = []

    for event_id, registro in registros.items():
        if registro["accion"].startswith("✅") or registro.get("reporte_manual"):
            continue  # Ya procesado o reportado

        tiempo = ahora - registro.get("timestamp", ahora)
        if tiempo < 6:
            continue  # No ha expirado

        vehiculo = registro.get("vehiculo")
        chapa = registro.get("chapa")
        rfid = registro.get("rfid")
        casco = registro.get("casco")

        falta = []
        if not vehiculo: falta.append("vehiculo")
        if not chapa: falta.append("chapa")
        if not rfid: falta.append("rfid")
        if vehiculo == "moto" and casco is None: falta.append("casco")

        if falta:
            razon = "incompleto_timeout_" + "_".join(falta)
            registro["accion"] = f"⏱️ Timeout: faltan {', '.join(falta)}"

            img_file = None
            casco_file = None
            files = {}

            try:
                # Imagen principal
                img_path = registro.get("img_path")
                if img_path and os.path.exists(img_path):
                    img_file = open(img_path, "rb")
                    files["foto"] = img_file

                # Imagen de casco
                casco_path = registro.get("foto_casco_path")
                if casco_path and os.path.exists(casco_path):
                    casco_file = open(casco_path, "rb")
                    files["foto_casco"] = casco_file

                payload = {
                    "event_id": event_id,
                    "chapa_detectada": chapa or "N/A",
                    "chapa_rfid": rfid or "N/A",
                    "casco": True if vehiculo != "moto" else not casco,
                    "razon": razon
                }

                print("⏱️ Reporting uncomplete event:", payload)
                res = requests.post("http://192.168.16.102:5050/recibir-imagen", data=payload, files=files)
                registro["reporte_manual"] = res.json()
                expirados.append(event_id)

            except Exception as e:
                print("❌ Error:", e)
                registro["reporte_manual"] = {"error": str(e)}

            finally:
                if img_file:
                    img_file.close()
                if casco_file:
                    casco_file.close()


    return {"expirados": expirados, "total": len(expirados)}


@app.get("/ver-registros")
def ver_registros():
    return registros