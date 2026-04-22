import sys
import os

# Añadir el directorio raíz al path para poder importar la app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.semestres import Semestre, Horario, GrupoSemestre

DATA = [
    {
        "nombre": "6:00 – 7:00 AM",
        "dia_1": "lunes", "dia_2": "miercoles", "dia_3": "martes", "dia_4": "jueves",
        "grupos": [
            {"nombre": "G. E Mixto 1", "sub_bloque": 1},
            {"nombre": "Atletismo 1", "sub_bloque": 1},
            {"nombre": "G. Caminata 13", "sub_bloque": 1},
            {"nombre": "G. E Mixto 2", "sub_bloque": 2},
            {"nombre": "Atletismo 2", "sub_bloque": 2},
            {"nombre": "G. Caminata 14", "sub_bloque": 2},
        ]
    },
    {
        "nombre": "7:00 – 8:00 PM",
        "dia_1": "lunes", "dia_2": "miercoles", "dia_3": "martes", "dia_4": "jueves",
        "grupos": [
            {"nombre": "G. Caminata 1", "sub_bloque": 1},
            {"nombre": "G. Caminata 3", "sub_bloque": 1},
            {"nombre": "G. Caminata 5", "sub_bloque": 1},
            {"nombre": "Atletismo 3", "sub_bloque": 1},
            {"nombre": "Basquetbol Mujeres 1", "sub_bloque": 1},
            {"nombre": "G. Entrenamiento Hombres 1", "sub_bloque": 1},
            {"nombre": "G. Entrenamiento Hombres 3", "sub_bloque": 1},
            {"nombre": "G. Entrenamiento Mujeres 1", "sub_bloque": 1},
            {"nombre": "G. Entrenamiento Mujeres 3", "sub_bloque": 1},
            {"nombre": "Voleibol 1", "sub_bloque": 1},
            {"nombre": "Voleibol 3", "sub_bloque": 1},
            {"nombre": "G. Caminata 2", "sub_bloque": 2},
            {"nombre": "G. Caminata 4", "sub_bloque": 2},
            {"nombre": "G. Caminata 6", "sub_bloque": 2},
            {"nombre": "Atletismo 4", "sub_bloque": 2},
            {"nombre": "Basquetbol Mujeres 2", "sub_bloque": 2},
            {"nombre": "G. Entrenamiento Hombres 2", "sub_bloque": 2},
            {"nombre": "G. Entrenamiento Hombres 4", "sub_bloque": 2},
            {"nombre": "G. Entrenamiento Mujeres 2", "sub_bloque": 2},
            {"nombre": "G. Entrenamiento Mujeres 4", "sub_bloque": 2},
            {"nombre": "Voleibol 2", "sub_bloque": 2},
            {"nombre": "Voleibol 4", "sub_bloque": 2},
        ]
    },
    {
        "nombre": "8:00 – 9:00 PM",
        "dia_1": "lunes", "dia_2": "miercoles", "dia_3": "martes", "dia_4": "jueves",
        "grupos": [
            {"nombre": "Grupo Caminata 7", "sub_bloque": 1},
            {"nombre": "Grupo Caminata 9", "sub_bloque": 1},
            {"nombre": "Grupo Caminata 11", "sub_bloque": 1},
            {"nombre": "Entrenamiento Mujeres 5", "sub_bloque": 1},
            {"nombre": "Entrenamiento Mujeres 7", "sub_bloque": 1},
            {"nombre": "Entrenamiento Varonil 5", "sub_bloque": 1},
            {"nombre": "Atletismo 5", "sub_bloque": 1},
            {"nombre": "Basquet Varonil 1", "sub_bloque": 1},
            {"nombre": "Voleibol 5", "sub_bloque": 1},
            {"nombre": "Voleibol 7", "sub_bloque": 1},
            {"nombre": "Grupo Caminata 8", "sub_bloque": 2},
            {"nombre": "Grupo Caminata 10", "sub_bloque": 2},
            {"nombre": "Grupo Caminata 12", "sub_bloque": 2},
            {"nombre": "Entrenamiento Mujeres 6", "sub_bloque": 2},
            {"nombre": "Entrenamiento Mujeres 8", "sub_bloque": 2},
            {"nombre": "Entrenamiento Varonil 6", "sub_bloque": 2},
            {"nombre": "Entrenamiento Varonil 8", "sub_bloque": 2},
            {"nombre": "Atletismo 6", "sub_bloque": 2},
            {"nombre": "Basquet Varonil 2", "sub_bloque": 2},
            {"nombre": "Voleibol 6", "sub_bloque": 2},
            {"nombre": "Voleibol 8", "sub_bloque": 2},
        ]
    }
]

def seed_semestre_2():
    db: Session = SessionLocal()
    try:
        # 1. Verificar semestre
        semestre_id = 2
        semestre = db.query(Semestre).filter(Semestre.id == semestre_id).first()
        if not semestre:
            print(f"Error: El semestre con ID {semestre_id} no existe.")
            return

        print(f"Semestre encontrado: {semestre.nombre}")

        # 2. Verificar horarios existentes
        horarios_existentes = db.query(Horario).filter(Horario.semestre_id == semestre_id).all()
        if horarios_existentes:
            count = len(horarios_existentes)
            confirm = input(f"El semestre {semestre_id} ya tiene {count} horarios. ¿Sobreescribir? (s/n): ")
            if confirm.lower() != 's':
                print("Cancelado.")
                return
            
            # Borrar horarios (y por cascade sus grupos)
            print("Eliminando datos previos...")
            for h in horarios_existentes:
                db.delete(h)
            db.commit()

        # 3. Insertar datos
        total_horarios = 0
        total_grupos = 0

        for h_data in DATA:
            print(f"Insertando horario: {h_data['nombre']}...", end=" ", flush=True)
            db_horario = Horario(
                semestre_id=semestre_id,
                nombre=h_data['nombre'],
                dia_1=h_data['dia_1'],
                dia_2=h_data['dia_2'],
                dia_3=h_data['dia_3'],
                dia_4=h_data['dia_4']
            )
            db.add(db_horario)
            db.commit()
            db.refresh(db_horario)
            print(f"OK (id={db_horario.id})")
            total_horarios += 1

            for g_data in h_data['grupos']:
                print(f"  {g_data['nombre']} (sub_bloque={g_data['sub_bloque']})...", end=" ", flush=True)
                db_grupo = GrupoSemestre(
                    semestre_id=semestre_id,
                    horario_id=db_horario.id,
                    nombre=g_data['nombre'],
                    tipo="Taller", # Por defecto según estructura
                    sub_bloque=g_data['sub_bloque']
                )
                db.add(db_grupo)
                print("OK")
                total_grupos += 1
            
            db.commit()

        print("\nSeed completado:")
        print(f"{total_horarios} horarios creados")
        print(f"{total_grupos} grupos creados")

    except Exception as e:
        db.rollback()
        print(f"\nError durante el seed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_semestre_2()
