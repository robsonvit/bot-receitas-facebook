import os
import sys
import json
import time
import random
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

def salvar_postado(post_id, postados_list):
    if post_id not in postados_list:
        postados_list.append(post_id)
    # Removido o limite de 200 para garantir que NUNCA repita publicações
    try:
        with open(POSTED_FILE, "w", encoding="utf-8") as f:
            json.dump(postados_list, f, indent=2)
        log.info(f"ID {post_id} salvo no histórico permanente.")
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

def extrair_midia(post):
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
                
    return media_url, tipo_midia

def buscar_e_postar():
    if not FB_PAGE_ID or not FB_TOKEN:
        log.error("Credenciais do Facebook não configuradas.")
        return

    postados_list = carregar_postados()
    postados_set = set(postados_list)
    
    feedparser.USER_AGENT = "BotReceitasFacebook/1.0"
    
    feeds_para_tentar = [
        "https://www.reddit.com/r/ComidasBR/new.rss",
        "https://www.reddit.com/r/ComidasBR/hot.rss",
        "https://www.reddit.com/r/ComidasBR/top.rss?t=month",
        "https://www.reddit.com/r/ComidasBR/top.rss?t=all",
        "https://www.reddit.com/r/ComidasBR/top.rss?t=year"
    ]
    
    post_escolhido = None
    
    for idx, url_reddit in enumerate(feeds_para_tentar):
        log.info(f"Buscando posts via RSS: {url_reddit}")
        feed = feedparser.parse(url_reddit)
        
        if getattr(feed, 'status', 0) == 429:
            log.warning(f"Rate limit (429) no feed {url_reddit}.")
            time.sleep(2)
            continue
            
        if not feed.entries:
            log.warning(f"Nenhum post retornado em {url_reddit}.")
            continue
            
        candidatos = []
        for post in feed.entries:
            if post.id in postados_set:
                continue
                
            media_url, tipo_midia = extrair_midia(post)
            if media_url:
                candidatos.append((post, media_url, tipo_midia))
                
        if candidatos:
            if idx == 0:
                # Se for o 'new', pega o primeiro da lista (o mais recente de todos)
                post_escolhido = candidatos[0]
                log.info(f"Encontrado {len(candidatos)} posts novos nunca postados. Pegando o mais recente.")
            else:
                # Se for fallback (hot, top), pega um aleatório dos que nunca foram postados
                post_escolhido = random.choice(candidatos)
                log.info(f"Fallback: Encontrado {len(candidatos)} posts antigos nunca postados. Escolhido um aleatório.")
            break
        else:
            log.info(f"Nenhum post inédito e com imagem encontrado no feed {url_reddit}.")
            time.sleep(2)
            
    if not post_escolhido:
        log.error("Todos os feeds foram checados e TODOS os posts já foram postados ou não possuem imagens suportadas. Aguarde novos posts no Reddit.")
        sys.exit(1)
        
    post, media_url, tipo_midia = post_escolhido
    post_id = post.id
    titulo = post.title
    mensagem_final = f"{titulo}".strip()
    
    log.info(f"Iniciando download da mídia escolhida: {media_url} (Post ID: {post_id})")
    
    try:
        r_media = requests.get(media_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        r_media.raise_for_status()
        
        caminho_local = "temp_media.jpg"
        with open(caminho_local, "wb") as f:
            f.write(r_media.content)
        log.info("Download concluído.")
    except Exception as e:
        log.error(f"Erro ao baixar imagem: {e}")
        sys.exit(1)

    sucesso = False
    if tipo_midia == "image":
        caminho_limpo = limpar_metadados_imagem(caminho_local)
        sucesso = publicar_imagem(FB_PAGE_ID, FB_TOKEN, caminho_limpo, mensagem_final)
        
    if sucesso:
        salvar_postado(post_id, postados_list)
        log.info("Postagem finalizada com sucesso e salva no histórico permanente.")
        sys.exit(0)
    else:
        log.error("Falha na etapa de publicação na API do Facebook.")
        sys.exit(1)

if __name__ == "__main__":
    buscar_e_postar()
