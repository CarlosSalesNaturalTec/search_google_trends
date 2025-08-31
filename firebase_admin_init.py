import firebase_admin
from firebase_admin import credentials, firestore
import os
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Pega o caminho para o arquivo de credenciais da variável de ambiente
cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

if not cred_path:
    raise ValueError("A variável de ambiente GOOGLE_APPLICATION_CREDENTIALS não está definida.")

try:
    # Inicializa o SDK do Firebase Admin com as credenciais
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    print("Firebase Admin SDK inicializado com sucesso.")
except Exception as e:
    print(f"Erro ao inicializar o Firebase Admin SDK: {e}")
    # Em um ambiente de produção, você pode querer lançar a exceção
    # raise e

# Obtém uma instância do cliente do Firestore
db = firestore.client()
