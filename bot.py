import os
import sys
import json
import time
import requests
import logging
import feedparser
import re
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

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
    if len(postados) > 200:
        postados = postados[-200:]
    try:
        with open(POSTED_FILE, "w", encoding="utf-8") as f:
            json.dump(postados, f, indent=2)
        log.info(f"ID {post_id} salvo no histórico.")
    except Exception as e:
        log.error(f"Erro ao salvar {POSTED_FILE}: {e}")

def limpar_metadados_imagem(caminho_imagem):
    try:
        img = Image.open(caminho_imagem)
        data = list(img.getdata())
        img_sem_exif = Image.new(img.mode, img.size)
        img_sem_exif.putdata(data)
        
        caminho_limpo = "clean_image.jpg"
        if img_sem_exif.mode in ("RGBA", "P"):
            img_sem_exif = img_sem_exif.convert("RGB")
            
        img_sem_exif.save(caminho_limpo, "JPEG", quality=95)
        log.info("Metadados da imagem removidos com sucesso.")
        return caminho_limpo
    except Exception as e:
        log.error(f"Erro ao limpar metadados da imagem: {e}")
        return caminho_imagem

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

def buscar_e_postar():
    if not FB_PAGE_ID or not FB_TOKEN:
        log.error("Credenciais do Facebook não configuradas.")
        return

    postados = carregar_postados()
    url_reddit = "https://www.reddit.com/r/ComidasBR/new.rss"
    
    feedparser.USER_AGENT = "BotReceitasFacebook/1.0"
    log.info("Buscando posts recentes via RSS usando feedparser...")
    feed = feedparser.parse(url_reddit)
    
    if getattr(feed, 'status', 0) == 429:
        log.error("Rate limit (429) atingido no Reddit. O IP atual está temporariamente bloqueado. Tente novamente mais tarde.")
        sys.exit(1)
        
    if not feed.entries:
        log.warning("Nenhum post encontrado ou erro ao acessar o feed.")
        sys.exit(1)

    for post in feed.entries:
        post_id = post.id
        
        if post_id in postados:
            continue
            
        titulo = post.title
        mensagem_final = f"{titulo}".strip()
        
        media_url = None
        tipo_midia = None
        
        if hasattr(post, 'media_thumbnail') and len(post.media_thumbnail) > 0:
            media_url = post.media_thumbnail[0]['url']
            tipo_midia = "image"
            
        if not media_url and hasattr(post, 'content'):
            for c in post.content:
                match = re.search(r'img src="([^"]+)"', c.value)
                if match:
                    media_url = match.group(1).replace('&amp;', '&')
                    tipo_midia = "image"
                    break
        
        if not media_url:
            log.info(f"Post {post_id} ignorado (sem imagem encontrada).")
            salvar_postado(post_id, postados)
            continue
            
        log.info(f"Mídia encontrada: {media_url} (Tipo: {tipo_midia})")
        
        try:
            log.info("Baixando mídia...")
            r_media = requests.get(media_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            r_media.raise_for_status()
            
            caminho_local = "temp_media.jpg"
            with open(caminho_local, "wb") as f:
                f.write(r_media.content)
            log.info("Download concluído.")
        except Exception as e:
            log.error(f"Erro ao baixar imagem: {e}")
            continue

        sucesso = False
        if tipo_midia == "image":
            caminho_limpo = limpar_metadados_imagem(caminho_local)
            sucesso = publicar_imagem(FB_PAGE_ID, FB_TOKEN, caminho_limpo, mensagem_final)
            
        if sucesso:
            salvar_postado(post_id, postados)
            log.info("Postagem finalizada! O bot enviou para o Facebook com sucesso.")
            sys.exit(0)
        else:
            log.error("Falha ao publicar. Tentando o próximo post...")

if __name__ == "__main__":
    buscar_e_postar()
