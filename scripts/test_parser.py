import sys
import os

# Add app to path
sys.path.append(os.getcwd())

from app.services.excel_parser import parse_excel
import logging

logging.basicConfig(level=logging.INFO)

def test_file(path):
    if not os.path.exists(path):
        print(f"Error: File {path} not found.")
        return

    print(f"Testing parser with: {path}")
    try:
        with open(path, 'rb') as f:
            contenido = f.read()

        resultado = parse_excel(contenido)
        print(f"\nHojas procesadas: {len(resultado)}")
        total_alumnos = 0
        for hoja in resultado:
            num_alumnos = len(hoja['alumnos'])
            total_alumnos += num_alumnos
            print(f"  - {hoja['nombre']}: {num_alumnos} alumnos (horario: {hoja['horario']})")
        
        print(f"\nTotal alumnos parseados: {total_alumnos}")
        
    except Exception as e:
        print(f"Error parseando el archivo: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/test_parser.py <ruta_al_excel>")
    else:
        test_file(sys.argv[1])
