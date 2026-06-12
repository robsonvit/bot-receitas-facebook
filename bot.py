import os
import sys
import json
import time
import random
import requests
import logging
import feedparser
import re
import subprocess
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

def limpar_metadados_video(caminho_video):
    try:
        caminho_limpo = "clean_video.mp4"
        cmd = [
            "ffmpeg", "-y", "-i", caminho_video,
            "-map_metadata", "-1", "-c:v", "copy", "-c:a", "copy", caminho_limpo
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            log.info("Metadados do vídeo removidos com sucesso.")
            return caminho_limpo
        else:
            log.warning(f"Falha ao limpar metadados do vídeo. Usando original. Erro: {res.stderr}")
            return caminho_video
    except Exception as e:
        log.error(f"Erro ao limpar metadados do vídeo: {e}")
        return caminho_video

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
    url = f"https://graph.facebook.com/v22.0/{page_id}/videos"
    payload = {
        "description": mensagem,
        "access_token": token
    }
    try:
        with open(caminho_video, "rb") as f:
            res = requests.post(url, data=payload, files={"source": f}, timeout=180).json()
            
        if res.get("id"):
            log.info(f"✅ Vídeo publicado com sucesso! Video ID: {res.get('id')}")
            return True
        else:
            log.error(f"❌ Erro ao publicar vídeo: {res}")
            return False
    except Exception as e:
        log.error(f"Erro na requisição de publicação de vídeo: {e}")
        return False

def extrair_midia(post):
    media_url = None
    tipo_midia = None
    
    # 1. Verifica se tem link de video do Reddit no HTML
    if hasattr(post, 'content'):
        for c in post.content:
            if 'v.redd.it' in c.value or 'youtube.com' in c.value or 'youtu.be' in c.value:
                tipo_midia = "video"
                media_url = post.link # Usamos a URL do post pro yt-dlp resolver
                return media_url, tipo_midia
    
    # 2. Thumbnail de imagem
    if hasattr(post, 'media_thumbnail') and len(post.media_thumbnail) > 0:
        media_url = post.media_thumbnail[0]['url']
        tipo_midia = "image"
        
    # 3. Tag img no conteudo
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
            
    if not post_escolhido:
        log.error("Nenhum VÍDEO ou IMAGEM novo encontrado para o teste.")
        sys.exit(1)
        
    post, media_url, tipo_midia = post_escolhido
    post_id = post.id
    titulo = post.title
    mensagem_final = f"{titulo}".strip()
    
    log.info(f"Iniciando download da mídia: {media_url} (Tipo: {tipo_midia})")
    
    sucesso = False
    
    try:
        if tipo_midia == "video":
            caminho_local = "temp_video.mp4"
            log.info("Baixando vídeo via yt-dlp...")
            cmd = [
                "yt-dlp",
                "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "-o", caminho_local,
                media_url
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                log.error(f"yt-dlp falhou: {res.stderr}")
                
                # FALLBACK RAPIDSAVE
                log.info("Tentando Fallback via RapidSave...")
                rs_url = f"https://rapidsave.com/info?url={media_url}"
                headers = {"User-Agent": "Mozilla/5.0"}
                rs_html = requests.get(rs_url, headers=headers).text
                
                # tenta extrair o link direto
                match = re.search(r'href="(https://[^"]+\.mp4[^"]*)"', rs_html)
                if not match:
                    match = re.search(r'href="(https://sd\.rapidsave\.com/download\.php[^"]*)"', rs_html)
                
                if match:
                    from urllib.parse import unquote
                    download_url = unquote(match.group(1).replace('&amp;', '&'))
                    log.info(f"Link RapidSave encontrado: {download_url}")
                    vid_res = requests.get(download_url, headers=headers)
                    with open(caminho_local, "wb") as f:
                        f.write(vid_res.content)
                    log.info("Vídeo baixado via RapidSave!")
                else:
                    log.error("RapidSave falhou.")
                    sys.exit(1)
            else:
                log.info("Download yt-dlp concluído com sucesso.")
                
            caminho_limpo = limpar_metadados_video(caminho_local)
            sucesso = publicar_video(FB_PAGE_ID, FB_TOKEN, caminho_limpo, mensagem_final)
            
        elif tipo_midia == "image":
            caminho_local = "temp_image.jpg"
            log.info("Baixando imagem...")
            img_res = requests.get(media_url)
            if img_res.status_code == 200:
                with open(caminho_local, "wb") as f:
                    f.write(img_res.content)
                log.info("Imagem baixada com sucesso.")
                caminho_limpo = limpar_metadados_imagem(caminho_local)
                sucesso = publicar_imagem(FB_PAGE_ID, FB_TOKEN, caminho_limpo, mensagem_final)
            else:
                log.error(f"Erro ao baixar imagem. Status: {img_res.status_code}")
                sys.exit(1)
                
    except Exception as e:
        log.error(f"Erro no fluxo de video: {e}")
        sys.exit(1)

    if sucesso:
        salvar_postado(post_id, postados_list)
        log.info("Postagem finalizada com sucesso!")
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    buscar_e_postar()
