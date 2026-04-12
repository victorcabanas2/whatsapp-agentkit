import asyncio, random
from datetime import datetime, timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent.memory import inicializar_db, async_session, Lead, Pedido
from sqlalchemy import select

NOMBRES = ["Susana Quevedo", "Victor Cabañas", "María González", "Carlos López", "Ana Martínez",
    "Juan Rodríguez", "Laura Fernández", "Diego Ramírez", "Sofia Díaz", "Miguel Ángel Torres",
    "Carmen Sánchez", "Roberto García", "Patricia Flores", "Fernando Morales", "Luisa Méndez",
    "Ricardo Navarro", "Valentina Castro", "Pablo Reyes", "Gabriela Silva", "Alejandro Rojas",
    "Beatriz Castillo", "Andrés Medina", "Catalina Vargas", "Eduardo Ramos", "Francisca Ibáñez",
    "Javier Peña", "Isabel Campos", "Mario Lucero", "Elena Parra", "Cristian Acuña",
    "Josefina Bustos", "Rafael Sepúlveda", "Magdalena Baeza", "Arturo Vásquez", "Margarita Cortés",
    "Gonzalo Salazar", "Rosario Bravo", "Ignacio Herrera", "Antonia Gómez", "Víctor Aguirre",
    "Matilde Escobar", "Luis Armando", "Micaela Sandoval", "Raúl Muñoz", "Dolores Valenzuela",
    "Gustavo Arias", "Eloísa Orellana", "Emilio Robles", "Herminia Chávez", "Isidro Carrasco"]

PRODUCTOS = ["WHOOP Band", "Therabody Elite", "Foreo Luna", "FAQ™ 211", "LED Therapy",
    "Smart Watch", "Fitness Band", "Massager", "Facial Brush", "LED Panel"]

async def main():
    await inicializar_db()
    print("✓ BD inicializada")
    
    # Crear leads
    async with async_session() as session:
        for nombre in NOMBRES:
            area = random.choice(['91','92','93','94','95','96','97','98','99'])
            numero = ''.join([str(random.randint(0,9)) for _ in range(7)])
            telefono = f"+595{area}{numero}"
            
            score = [random.randint(70,95), random.randint(50,69), random.randint(20,49)][
                [0.2, 0.33, 0.47].index(min([0.2, 0.33, 0.47], key=lambda x: abs(x-random.random())))]
            intencion = ["hot","warm","cold"][[0.2, 0.33, 0.47].index(min([0.2, 0.33, 0.47], key=lambda x: abs(x-random.random())))]
            
            dias = random.randint(1, 90)
            primer_contacto = datetime.utcnow() - timedelta(days=dias)
            
            lead = Lead(
                telefono=telefono,
                nombre=nombre,
                primer_contacto=primer_contacto,
                ultimo_mensaje=primer_contacto + timedelta(hours=random.randint(1,500)),
                score=score,
                intencion=intencion,
                urgencia=random.choice(['baja','media','alta']),
                fue_cliente=random.random() < 0.15,
            )
            session.add(lead)
        await session.commit()
    
    print(f"✅ {len(NOMBRES)} leads creados")
    
    # Crear pedidos
    async with async_session() as session:
        resultado = await session.execute(select(Lead))
        leads = resultado.scalars().all()
        
        for lead in leads[:15]:
            if random.random() < 0.7:
                pedido = Pedido(
                    telefono=lead.telefono,
                    producto=random.choice(PRODUCTOS),
                    precio=str(random.randint(200000, 5000000) // 100 * 100),
                    metodo_pago=random.choice(['transferencia','efectivo','pagopar']),
                    fecha_pedido=datetime.utcnow() - timedelta(days=random.randint(1,30)),
                    nombre_cliente=lead.nombre,
                    estado=random.choice(['pendiente','pagado','entregado']),
                )
                session.add(pedido)
        await session.commit()
    
    async with async_session() as session:
        leads_c = len((await session.execute(select(Lead))).scalars().all())
        pedidos_c = len((await session.execute(select(Pedido))).scalars().all())
    
    print(f"✅ {pedidos_c} pedidos creados")
    print(f"\n📊 Dashboard: {leads_c} leads, {pedidos_c} pedidos")

asyncio.run(main())
