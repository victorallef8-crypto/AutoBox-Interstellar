from __future__ import annotations
import cv2
import numpy as np

def locate_boxes(frame_bgr: np.ndarray, sample_bgr: np.ndarray,
                 threshold: float = 0.90,
                 require_bright: bool = True) -> list[tuple[int, int, float]]:
    """Retorna candidatos (x,y,confianca) em pixels relativos a frame_bgr.

    Busca em algumas escalas para tolerar pequenas variacoes de renderizacao.
    Nao faz cliques nem depende da interface grafica.
    """
    if frame_bgr is None or sample_bgr is None:
        return []
    frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    sample_gray = cv2.cvtColor(sample_bgr, cv2.COLOR_BGR2GRAY)
    height, width = frame_gray.shape
    proposals: list[tuple[int, int, float]] = []

    for scale in (0.85, 1.0, 1.15):
        sw = max(9, round(sample_gray.shape[1] * scale))
        sh = max(9, round(sample_gray.shape[0] * scale))
        if sw >= width or sh >= height:
            continue
        resized = cv2.resize(sample_gray, (sw, sh), interpolation=cv2.INTER_LINEAR)
        if float(resized.std()) < 8.0:
            continue
        scores = cv2.matchTemplate(frame_gray, resized, cv2.TM_CCOEFF_NORMED)
        # Picos locais para evitar centenas de candidatos por um unico objeto.
        neighborhood = max(11, min(sw, sh) // 2)
        maxima = cv2.dilate(scores, np.ones((neighborhood, neighborhood), np.uint8))
        ys, xs = np.where((scores >= threshold) & (scores >= maxima - 1e-6))
        for y, x in zip(ys.tolist(), xs.tolist()):
            cx, cy = x + sw // 2, y + sh // 2
            # Exige que haja um centro luminoso, nao so a mesma textura de fundo.
            patch = frame_bgr[max(0, cy - 4): min(height, cy + 5),
                              max(0, cx - 4): min(width, cx + 5)]
            if patch.size and (not require_bright or int(np.max(np.min(patch, axis=2))) >= 175):
                proposals.append((cx, cy, float(scores[y, x])))

    proposals.sort(key=lambda p: p[2], reverse=True)
    output: list[tuple[int, int, float]] = []
    for x, y, confidence in proposals:
        if all((x - ox) ** 2 + (y - oy) ** 2 >= 24 ** 2 for ox, oy, _ in output):
            output.append((x, y, confidence))
        if len(output) >= 40:
            break
    return output

def radiation_visible(frame_bgr: np.ndarray) -> bool:
    """Aviso vermelho da faixa superior, sem OCR ou templates externos."""
    height, width = frame_bgr.shape[:2]
    top = frame_bgr[0:max(1, int(height * .18)),
                    int(width * .32):int(width * .68)]
    if top.size == 0:
        return False
    b, g, r = cv2.split(top)
    red = (r > 90) & (r.astype(np.int16) > 2 * g.astype(np.int16)) & (
        r.astype(np.int16) > 1.5 * b.astype(np.int16))
    return int(np.count_nonzero(red)) > 950

def find_death_panel(frame_bgr: np.ndarray) -> tuple[int, int, int, int] | None:
    """Procura a caixa de morte ao centro: texto vermelho + painel retangular."""
    height, width = frame_bgr.shape[:2]
    crop_x, crop_y = int(width * .23), int(height * .24)
    crop = frame_bgr[crop_y:int(height * .81), crop_x:int(width * .77)]
    if crop.size == 0:
        return None
    b, g, r = cv2.split(crop)
    red_text = (r > 145) & (r.astype(np.int16) > 2 * g.astype(np.int16)) & (
        r.astype(np.int16) > 1.7 * b.astype(np.int16))
    # Nao confundir com a faixa RADIATION ZONE, que fica la no topo.
    ys, xs = np.nonzero(red_text)
    if len(xs) < 80:
        return None
    red_in_mid = ((xs > crop.shape[1] * .3) & (xs < crop.shape[1] * .7) &
                  (ys > crop.shape[0] * .14) & (ys < crop.shape[0] * .43))
    if int(red_in_mid.sum()) < 65:
        return None

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    mask = ((gray >= 12) & (gray < 140)).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    options = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        abs_x, abs_y = x + crop_x, y + crop_y
        if not (.18 * width <= w <= .42 * width and
                .23 * height <= h <= .53 * height):
            continue
        if abs((abs_x + w / 2) - width / 2) > width * .15:
            continue
        options.append((abs_x, abs_y, w, h))
    return max(options, key=lambda item: item[2] * item[3]) if options else None

def new_reward_message(before_bgr: np.ndarray, after_bgr: np.ndarray) -> bool:
    """Detecta uma linha clara *nova* na area de notificacoes marcada.

    Compara com a imagem feita ANTES do clique. Mensagens antigas que ainda
    estejam na tela nao podem disparar uma segunda coleta. O jogador deve
    selecionar apenas as linhas 'You received', sem barras nem animacoes.
    Nao exige OCR nem leitura de memoria do jogo.
    """
    if (before_bgr is None or after_bgr is None or
            before_bgr.shape != after_bgr.shape or before_bgr.ndim != 3):
        return False

    def light_text(image):
        # O texto do print e cinza-claro/branco em fundo preto; ignora
        # mensagens coloridas e pequenas estrelas isoladas.
        low = np.min(image, axis=2)
        high = np.max(image, axis=2)
        return (low >= 125) & ((high.astype(np.int16) - low) <= 42)

    added = light_text(after_bgr) & ~light_text(before_bgr)
    if int(np.count_nonzero(added)) < 42:
        return False
    rows = np.flatnonzero(np.count_nonzero(added, axis=1) >= 8)
    columns = np.flatnonzero(np.any(added, axis=0))
    # Texto de uma notificacao ocupa varias linhas e dezenas de pixels
    # horizontais, ao contrario de estrelas/particulas individuais.
    return (len(rows) >= 3 and len(columns) >= 28 and
            int(columns[-1] - columns[0]) >= 48)
