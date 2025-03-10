import json
import datetime
import pandas as pd
import boto3
from bs4 import BeautifulSoup

# Configuración de S3
s3_client = boto3.client("s3")
SOURCE_BUCKET = "parcialbigdatauwu"
DESTINATION_BUCKET = "casas-finales-parseadas"

def clean_price(price):
    """Limpia y convierte el precio a un formato numérico."""
    if price and isinstance(price, str):
        return "".join(filter(str.isdigit, price))
    return "N/A"

def extract_number(value):
    """Extrae valores numéricos (como m²) de un string."""
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return "N/A"

def extract_data(html_content):
    """Extrae datos de apartaestudios desde el JSON o etiquetas <a> en el HTML."""
    soup = BeautifulSoup(html_content, "html.parser")
    fecha_descarga = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    registros = []

    # Intentar extraer datos desde el JSON-LD
    script_tag = soup.find("script", type="application/ld+json")
    if script_tag:
        try:
            data = json.loads(script_tag.string)
            apartaestudios = data[0].get("about", [])
            for apt in apartaestudios:
                barrio = apt["address"].get("addressLocality", "N/A")
                precio = clean_price(apt.get("offers", {}).get("price", "N/A"))
                num_habitaciones = apt.get("numberOfBedrooms", "N/A")
                num_banos = apt.get("numberOfBathroomsTotal", "N/A")
                mts2 = extract_number(apt.get("floorSize", {}).get("value", "N/A"))
                
                registros.append([fecha_descarga, barrio, precio, num_habitaciones, num_banos, mts2])
        except json.JSONDecodeError:
            print("Error al procesar JSON. Se intentará extraer desde etiquetas <a>.")

    # Si no se encontraron datos en JSON, buscar en las etiquetas <a>
    if not registros:
        property_cards = soup.find_all("a", class_="listing listing-card")
        for card in property_cards:
            titulo = card.get("title", "N/A")
            ubicacion = card.get("data-location", "N/A")
            precio = clean_price(card.get("data-price", "N/A"))
            num_habitaciones = card.get("data-rooms", "N/A")
            mts2 = extract_number(card.get("data-floorarea", "N/A"))

            registros.append([fecha_descarga, titulo, ubicacion, precio, num_habitaciones, "N/A", mts2])

    return registros

def save_to_s3(data, filename):
    """Guarda los datos extraídos en un CSV y lo sube a S3."""
    csv_content = "FechaDescarga,Barrio,Valor,NumHabitaciones,NumBanos,mts2\n"
    csv_content += "\n".join([",".join(map(str, row)) for row in data])

    s3_client.put_object(
        Bucket=DESTINATION_BUCKET,
        Key=filename,
        Body=csv_content.encode("utf-8"),
        ContentType="text/csv"
    )
    print(f"Archivo {filename} guardado en S3 en el bucket {DESTINATION_BUCKET}.")

def app(event, context):
    """Maneja la ejecución del Lambda cuando se sube un archivo HTML a S3."""
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        if bucket == SOURCE_BUCKET:
            response = s3_client.get_object(Bucket=bucket, Key=key)
            html_content = response["Body"].read().decode("utf-8")

            # Extraer datos del HTML
            data = extract_data(html_content)

            # Guardar en el segundo bucket
            if data:
                today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
                csv_filename = f"{today}.csv"
                save_to_s3(data, csv_filename)

                return {
                    "statusCode": 200,
                    "body": f"Archivo procesado y guardado en s3://{DESTINATION_BUCKET}/{csv_filename}"
                }
            else:
                return {
                    "statusCode": 400,
                    "body": "No se encontraron datos en el HTML."
                }
