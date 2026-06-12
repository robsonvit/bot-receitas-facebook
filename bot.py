import os
import sys
import json
import time
import requests
import logging
from io import BytesIO
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Configurações do Facebook (serão pegas do GitHub Secrets)
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_TOKEN = os.environ.get("FB_TOKEN")

POSTED_FILE = "posted.json"

def carregar_postados():
    if not os.path.exists(POSTED_FILE):
        return []
    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Erro ao ler {POSTED_FILE}: {e}")
        return []

def salvar_postado(post_id, postados):
    postados.append(post_id)
    # Mantém apenas os últimos 200 IDs para o arquivo não crescer infinitamente
    if len(postados) > 200:
        postados = postados[-200:]
    try:
        with open(POSTED_FILE, "w", encoding="utf-8") as f:
            json.dump(postados, f, indent=2)
        log.info(f"ID {post_id} salvo no histórico.")
    except Exception as e:
        log.error(f"Erro ao salvar {POSTED_FILE}: {e}")

def limpar_metadados_imagem(caminho_imagem):
    """Abre a imagem com Pillow e salva novamente sem os dados EXIF."""
    try:
        img = Image.open(caminho_imagem)
        data = list(img.getdata())
        img_sem_exif = Image.new(img.mode, img.size)
        img_sem_exif.putdata(data)
        
        caminho_limpo = "clean_image.jpg"
        # Convert to RGB Se for RGBA (PNG com transparência) para salvar como JPG
        if img_sem_exif.mode in ("RGBA", "P"):
            img_sem_exif = img_sem_exif.convert("RGB")
            
        img_sem_exif.save(caminho_limpo, "JPEG", quality=95)
        log.info("Metadados da imagem removidos com sucesso.")
        return caminho_limpo
    except Exception as e:
        log.error(f"Erro ao limpar metadados da imagem: {e}")
        return caminho_imagem # Fallback para a original

def publicar_imagem(page_id, token, caminho_imagem, mensagem):
    log.info("Iniciando publicação de IMAGEM no Facebook...")
    url = f"https://graph.facebook.com/v22.0/{page_id}/photos"
    payload = {
        "message": mensagem,
        "access_token": token
    }
    try:
        with open(caminho_imagem, "rb") as f:
            res = requests.post(url, data=payload, files={"source": f}, timeout=60).json()
            
        if res.get("id"):
            log.info(f"✅ Imagem publicada com sucesso! Post ID: {res.get('id')}")
            return True
        else:
            log.error(f"❌ Erro ao publicar imagem: {res}")
            return False
    except Exception as e:
        log.error(f"Erro na requisição de publicação de imagem: {e}")
        return False

def publicar_video(page_id, token, caminho_video, mensagem):
    log.info("Iniciando publicação de VÍDEO no Facebook...")
    # Usando o endpoint básico de vídeos para simplificar
    url = f"https://graph.facebook.com/v22.0/{page_id}/videos"
    payload = {
        "description": mensagem,
        "access_token": token
    }
    try:
        with open(caminho_video, "rb") as f:
            res = requests.post(url, data=payload, files={"source": f}, timeout=120).json()
            
        if res.get("id"):
            log.info(f"✅ Vídeo publicado com sucesso! Video ID: {res.get('id')}")
            return True
        else:
            log.error(f"❌ Erro ao publicar vídeo: {res}")
            return False
    except Exception as e:
        log.error(f"Erro na requisição de publicação de vídeo: {e}")
        return False

def buscar_e_postar():
    if not FB_PAGE_ID or not FB_TOKEN:
        log.error("Credenciais do Facebook não configuradas. Verifique o .env ou os Secrets do GitHub.")
        return

    postados = carregar_postados()
    
    url_reddit = "https://www.reddit.com/r/ComidasBR/new.json?limit=15"
    headers = {
        "User-Agent": "Bot:ReceitasFacebookBot:v1.0.0 (by /u/robsonvit)"
    }
    
    log.info("Buscando posts recentes no r/ComidasBR...")
    try:
        req = requests.get(url_reddit, headers=headers, timeout=15)
        req.raise_for_status()
        dados = req.json()
    except Exception as e:
        log.error(f"Erro ao acessar Reddit: {e}")
        sys.exit(1)

    posts = dados.get("data", {}).get("children", [])
    
    for post in posts:
        post_data = post["data"]
        post_id = post_data["id"]
        
        if post_id in postados:
            continue
            
        titulo = post_data.get("title", "")
        # A legenda extra (body) se existir
        texto = post_data.get("selftext", "")
        
        mensagem_final = f"{titulo}\n\n{texto}".strip()
        
        media_url = None
        tipo_midia = None
        
        # Verifica se é vídeo
        if post_data.get("is_video") and "media" in post_data and post_data["media"]:
            media_url = post_data["media"]["reddit_video"]["fallback_url"]
            tipo_midia = "video"
        # Verifica se é imagem direta
        elif post_data.get("url", "").endswith((".jpg", ".jpeg", ".png")):
            media_url = post_data["url"]
            tipo_midia = "image"
        # Verifica galeria de imagens (pega a primeira)
        elif "media_metadata" in post_data:
            metadata = post_data["media_metadata"]
            primeira_key = list(metadata.keys())[0]
            if "s" in metadata[primeira_key] and "u" in metadata[primeira_key]["s"]:
                # Reddit substitui os & por &amp; nas URLs de media_metadata
                media_url = metadata[primeira_key]["s"]["u"].replace("&amp;", "&")
                tipo_midia = "image"
        
        if not media_url:
            log.info(f"Post {post_id} ignorado (sem mídia suportada).")
            # Adiciona aos postados para não tentar novamente no futuro
            salvar_postado(post_id, postados)
            continue
            
        log.info(f"Mídia encontrada: {media_url} (Tipo: {tipo_midia})")
        
        # Baixa a mídia
        try:
            log.info("Baixando mídia...")
            r_media = requests.get(media_url, headers=headers, timeout=30)
            r_media.raise_for_status()
            
            caminho_local = "temp_media.mp4" if tipo_midia == "video" else "temp_media.jpg"
            with open(caminho_local, "wb") as f:
                f.write(r_media.content)
            log.info("Download concluído.")
        except Exception as e:
            log.error(f"Erro ao baixar mídia do post {post_id}: {e}")
            continue

        sucesso = False
        
        if tipo_midia == "image":
            caminho_limpo = limpar_metadados_imagem(caminho_local)
            sucesso = publicar_imagem(FB_PAGE_ID, FB_TOKEN, caminho_limpo, mensagem_final)
        elif tipo_midia == "video":
            # Para vídeos postamos direto (O Facebook já remove metadados no upload)
            sucesso = publicar_video(FB_PAGE_ID, FB_TOKEN, caminho_local, mensagem_final)
            
        if sucesso:
            salvar_postado(post_id, postados)
            log.info("Bot finalizou a postagem. Encerrando execução para postar apenas 1 por vez.")
            break # Posta apenas 1 por vez
        else:
            log.error("Falha ao publicar. Tentando o próximo post...")

if __name__ == "__main__":
    buscar_e_postar()
