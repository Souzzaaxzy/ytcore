# ytcore

Cliente YouTube **100% independente**: fala direto com a API interna do YouTube
(**InnerTube**, a mesma que o site e o app usam) usando **só a biblioteca padrão
do Python**. **Sem yt-dlp.** Só o ffmpeg (opcional) pra gerar o áudio.

```python
from ytcore import YouTube

yt = YouTube()

# buscar
track = yt.search_one("daft punk instant crush")
print(track.title, track.duration_str, track.thumbnail)

# URL direta do áudio (googlevideo) — pra jogar no seu ffmpeg
print(track.audio_url)

# baixar: áudio + capa
result = yt.fetch(track.id, out_dir="downloads", fmt="mp3")
print(result.audio_path, result.cover_path)
```

## Como funciona (e por que não precisa de yt-dlp)

O yt-dlp existe pra lidar com a miríade de truques do YouTube. Aqui usamos o
caminho mais direto:

1. **Busca** → `youtubei/v1/search` com o client `WEB`.
2. **Player** → `youtubei/v1/player` com o client **`ANDROID_VR`**, que devolve
   as **URLs de áudio diretas**, sem cipher de assinatura e sem token de
   proof-of-origin. É por isso que não precisamos de runtime JS nem solver.
3. **Download** → o ffmpeg lê a URL direta (ou o `urllib` baixa e o ffmpeg
   converte).

Zero dependências obrigatórias. `ffmpeg` só é preciso pra produzir arquivos de
áudio (a URL do stream e os metadados funcionam sem ele).

## Instalação

```bash
pip install -e ".[ffmpeg]"     # inclui o ffmpeg estático (imageio-ffmpeg)
```

Sem ffmpeg no sistema, a lib usa o binário estático do `imageio-ffmpeg`
(instalável por pip, não precisa de root). Se já tem ffmpeg, `pip install -e .`
basta.

## O que dá pra pegar

| Campo | Onde |
|---|---|
| Título, canal, duração, views | `Track` |
| Thumbnail (URL) + todas resoluções | `Track.thumbnail`, `Track.thumbnails` |
| **URLs de áudio diretas** (itag, codec, bitrate) | `Track.audio_formats`, `Track.audio_url` |
| Melhor stream de áudio | `Track.best_audio()` |
| Arquivo de áudio | `yt.download()`, `yt.fetch()` |
| Capa | `Downloader.download_cover()` |

## Fluxos

### Só metadados / URL do stream (sem baixar)

```python
yt = YouTube()
track = yt.get("dQw4w9WgXcQ")
print(track.audio_url)
for f in track.audio_formats:
    print(f.itag, f.container, f.codec, f.kbps, "kbps")
```

### Baixar e converter

```python
from ytcore import YouTube, FFmpeg

yt = YouTube()
track = yt.get("dQw4w9WgXcQ")

# ffmpeg lê a URL direto
yt.downloader.stream_to_file(track, "musica.mp3", fmt="mp3", bitrate="192k")

# ou: cortar um trecho
yt.downloader.stream_to_file(track, "trecho.mp3", fmt="mp3", duration=15, start=30)

# ou: baixar os bytes com urllib e converter
yt.downloader.download_bytes(track, "cru.webm")
FFmpeg().convert("cru.webm", "final.mp3", fmt="mp3")
```

### Busca + download numa chamada

```python
from ytcore import YouTube

result = YouTube().fetch("nome da musica", out_dir="dl", fmt="mp3")
# result.audio_path, result.cover_path, result.title, result.artist, result.duration
```

## Limites (seja honesto consigo mesmo)

Testei 20 músicas de ponta a ponta. Resultado:

| Estágio | Resultado |
|---|---|
| Busca | **20/20** |
| Extração (URLs de áudio) | **20/20** |
| Download do arquivo | **0/20** (HTTP 403) |

O download falha porque o **googlevideo bloqueia IP de datacenter**. Isso **não
é bug da lib**: rodei o mesmo vídeo, do mesmo IP, com o **yt-dlp** e ele
**também deu 403**. O CDN do YouTube recusa requisições de IPs de nuvem/VPS.

Do que dá pra fazer sobre isso:

- **IP residencial** → costuma funcionar direto.
- **Cookies** → ajudam na extração, mas o 403 do CDN persiste de datacenter.
- **Proxy residencial** → a saída confiável para rodar em VPS.

A lib detecta o 403 e levanta um `DownloadError` explicando exatamente isso, em
vez de um stack trace cru.

Outros limites:

- **A API interna não é oficial.** O YouTube pode mudar o InnerTube a qualquer
  momento (os clients `VISIONOS`/`ANDROID_VR` mudam de comportamento com
  frequência). Essa independência tem esse preço.
- Baixe só o que você tem direito: seus vídeos, CC ou domínio público.

## Estrutura

```
ytcore/
  clients.py     clientes InnerTube (WEB para busca, ANDROID_VR para player)
  client.py      InnerTube: search, player, get, formats, stream_url
  models.py      Track / Format / Thumbnail
  download.py    Downloader: stream->ffmpeg, download_bytes, cover
  ffmpeg.py      localiza o ffmpeg e converte
  parse.py       navegação nos renderers, duração, ids
  transport.py   urllib (padrão) + fake pra testes
```

## Testes

```bash
pytest
```

Offline: um transporte falso alimenta os payloads; o parsing, os modelos e o
ffmpeg são código real (o teste de conversão gera áudio de verdade).

## Licença

MIT.
