import re
from functools import lru_cache
from pathlib import Path
import cv2
import numpy as np


@lru_cache(maxsize=4)
def load_template(path):
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f'Template image missing: {path}')
    return image


def surrounding_ink(gray, template, grid, center, config):
    """Conservative cancellation clues, never an automatic answer correction."""
    x,y = center
    bw,bh = grid['sample_box']
    rx,ry = int(bw/2+9),int(bh/2+11)
    left,top = max(0,int(x)-rx),max(0,int(y)-ry)
    right,bottom = min(gray.shape[1],int(x)+rx+1),min(gray.shape[0],int(y)+ry+1)
    patch = gray[top:bottom,left:right]
    reference = template[top:bottom,left:right]
    ink = ((reference.astype(np.int16)-patch.astype(np.int16) > config.get('extra_ink_difference',45)) &
           (patch < config.get('extra_ink_threshold',180))).astype(np.uint8)*255
    yy,xx = np.ogrid[top:bottom,left:right]
    outside = (abs(xx-x)>bw/2+3) | (abs(yy-y)>bh/2+3)
    count = int(np.count_nonzero(ink[outside]))
    slopes = set()
    lines = cv2.HoughLinesP(ink,1,np.pi/180,threshold=8,minLineLength=12,maxLineGap=3)
    if lines is not None:
        for x1,y1,x2,y2 in lines.reshape(-1,4):
            dx,dy = int(x2-x1),int(y2-y1)
            if dx and .35 <= abs(dy/dx) <= 3 and min(y1,y2)+top < y-bh/2-2 and max(y1,y2)+top > y+bh/2+2:
                slopes.add(1 if dx*dy>0 else -1)
    return {'outside_ink_pixels':count, 'cross_suspected':len(slopes)==2}


def pages(path):
    if path.suffix.lower() == '.pdf':
        import fitz
        with fitz.open(path) as doc:
            for index, page in enumerate(doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False, colorspace=fitz.csRGB)
                yield index+1, cv2.cvtColor(np.frombuffer(pix.samples, np.uint8).reshape(pix.height,pix.width,3), cv2.COLOR_RGB2GRAY)
    else:
        from PIL import Image, ImageOps, ImageSequence
        with Image.open(path) as doc:
            for index, frame in enumerate(ImageSequence.Iterator(doc)):
                yield index+1, np.array(ImageOps.exif_transpose(frame).convert('L'))


def align(gray, config):
    w,h = config['page_size']
    scaled = cv2.resize(gray, (w,h))
    if config.get('template_image'):
        template = load_template(config['template_image'])
        if template is None or template.shape != (h, w):
            raise ValueError('Template image missing or has incorrect dimensions')
        orb = cv2.ORB_create(nfeatures=7000)
        source_keys, source_desc = orb.detectAndCompute(scaled, None)
        target_keys, target_desc = orb.detectAndCompute(template, None)
        if source_desc is None or target_desc is None:
            raise ValueError('Insufficient features to register sheet')
        pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(source_desc, target_desc, k=2)
        matches = [m for pair in pairs if len(pair) == 2 for m,n in [pair] if m.distance < .7*n.distance]
        if len(matches) < 20:
            raise ValueError('Sheet does not match the configured template')
        source = np.float32([source_keys[m.queryIdx].pt for m in matches])
        target = np.float32([target_keys[m.trainIdx].pt for m in matches])
        matrix, inliers = cv2.findHomography(source, target, cv2.RANSAC, 3)
        if matrix is None or int(inliers.sum()) < 20 or float(inliers.mean()) < .4:
            raise ValueError('Unreliable template registration; manual review required')
        matched = target[inliers.ravel().astype(bool)]
        if np.ptp(matched[:,0]) < w*.35 or np.ptp(matched[:,1]) < h*.35:
            raise ValueError('Registration features do not cover enough of the sheet')
        corners = np.float32([[[0,0],[w,0],[w,h],[0,h]]])
        projected = cv2.perspectiveTransform(corners, matrix)[0]
        if np.max(np.linalg.norm(projected-corners[0],axis=1)) > min(w,h)*.2:
            raise ValueError('Sheet rotation/crop exceeds supported registration range')
        return cv2.warpPerspective(scaled, matrix, (w,h), borderValue=255)
    if not config.get('fiducials'):
        return scaled
    _, binary = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    contours,_ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        x,y,cw,ch = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if 12 <= cw <= w*.12 and .7 < cw/ch < 1.3 and area/(cw*ch) > .75:
            candidates.append((x+cw/2,y+ch/2))
    chosen = []
    for expected in config['fiducials']:
        nearby = sorted(candidates, key=lambda p:(p[0]-expected[0])**2+(p[1]-expected[1])**2)
        if not nearby or np.linalg.norm(np.array(nearby[0])-expected) > min(w,h)*.15:
            raise ValueError('Registration marker missing; sheet needs manual review')
        chosen.append(nearby[0])
    if len(set(chosen)) != 4:
        raise ValueError('Registration requires four distinct markers')
    matrix = cv2.getPerspectiveTransform(np.float32(chosen), np.float32(config['fiducials']))
    return cv2.warpPerspective(scaled, matrix, (w,h), borderValue=255)


def detect(gray, grid, config):
    radius = grid.get('radius', config.get('radius', 10)) * .65
    densities = {}
    for label,(x,y) in zip(grid['labels'],grid['centers']):
        # Crop before sampling so cost scales with mark size, not page size.
        if grid.get('sample_box'):
            bw,bh = grid['sample_box']
            left,right = int(round(x-bw/2)),int(round(x+bw/2))
            top,bottom = int(round(y-bh/2)),int(round(y+bh/2))
            patch = gray[max(0,top):min(gray.shape[0],bottom), max(0,left):min(gray.shape[1],right)]
            pixels = patch.ravel()
        else:
            left,right = int(x-radius),int(x+radius)+1
            top,bottom = int(y-radius),int(y+radius)+1
            left,top = max(0,left),max(0,top)
            right,bottom = min(gray.shape[1],right),min(gray.shape[0],bottom)
            yy,xx = np.ogrid[top:bottom,left:right]
            mask = (xx-x)**2+(yy-y)**2 <= radius**2
            pixels = gray[top:bottom,left:right][mask]
        if not pixels.size:
            raise ValueError('Mark sampling region is empty')
        densities[label] = float(np.mean(pixels < config.get('pixel_threshold', 150)))
    threshold = config.get('density_threshold', .35)
    selected = [label for label,density in densities.items() if density >= threshold]
    uncertain = any(abs(d-threshold) < config.get('review_margin', .1) for d in densities.values())
    reasons = []
    if not selected:
        reasons.append('blank')
    elif len(selected) > 1:
        reasons.append('multiple')
    if uncertain:
        reasons.append('uncertain_density')
    # Traces below the selection threshold can be faint fills, erasures, or partial pen marks.
    if any(config.get('faint_mark_threshold', .08) <= d < threshold for d in densities.values()):
        reasons.append('faint_or_partial_mark')
    clues = {}
    if grid.get('sample_box') and config.get('template_image') and config.get('check_surrounding_ink', True):
        template = load_template(config['template_image'])
        for label,center in zip(grid['labels'],grid['centers']):
            clue = surrounding_ink(gray,template,grid,center,config)
            clues[label] = clue
            if clue['cross_suspected']:
                reasons.append('possible_cross_out')
            elif clue['outside_ink_pixels'] >= config.get('outside_ink_min_pixels', 12):
                reasons.append('stray_ink_or_cancellation')
    crossed = [label for label,clue in clues.items() if clue['cross_suspected']]
    remaining = [label for label in selected if label not in crossed]
    return {'selected':selected, 'raw_selected':list(selected), 'densities':densities,
            'uncertain':uncertain, 'mark_clues':clues, 'review_reasons':list(dict.fromkeys(reasons)),
            'suggested_selected':remaining if crossed and len(remaining)==1 else None}



def metadata(gray, config, log, evidence_dir=None, evidence_prefix="sheet"):
    result = {}
    details = {}
    for name, zone in config.get('metadata', {}).items():
        if zone['mode'] == 'bubble':
            chars = []
            for index, col in enumerate(zone['columns']):
                reading = detect(gray, col, config)
                if len(reading['selected']) != 1 or reading['uncertain']:
                    chars.append('?')
                    log('metadata_unrecognized', field=name, column=index, reading=reading)
                else:
                    chars.append(reading['selected'][0])
            result[name] = ''.join(chars)
        else:
            x,y,w,h = zone['box']
            crop = gray[y:y+h,x:x+w]
            detail = {'text':'', 'confidence':None, 'status':'error', 'box':zone['box']}
            details[name] = detail
            if evidence_dir is not None:
                ex,ey,ew,eh = zone.get('evidence_box',zone['box'])
                evidence = gray[ey:ey+eh,ex:ex+ew]
                directory = Path(evidence_dir)
                directory.mkdir(parents=True, exist_ok=True)
                # Use positional field IDs rather than untrusted field names in filenames.
                destination = directory / f'{evidence_prefix}-field-{len(details):02d}.png'
                if not cv2.imwrite(str(destination), evidence):
                    raise OSError(f'Could not save metadata evidence: {destination}')
                detail['crop'] = str(destination.resolve())
            try:
                from .ocr import recognize
                text = recognize(crop, config.get('ocr_engine','auto'))
                detail['engine'] = text.get('engine','unknown')
                words = [(word,float(conf)) for word,conf in zip(text['text'], text['conf']) if word.strip()]
                value = ' '.join(word for word,_ in words).strip()
                raw_value = value
                # Canonicalize spacing/case only; never guess ambiguous handwriting.
                if name in ('class', 'student_id'):
                    value = re.sub(r'\s+', '', value).upper()
                result[name] = value
                detail['raw_text'] = raw_value
                detail.update(text=value, confidence=min((conf for _,conf in words), default=None), status='recognized')
                if not value or any(conf < zone.get('min_confidence', 70) for _,conf in words) or not re.fullmatch({'class': r'[0-9]+[A-Z]', 'student_id': r'[0-9]+'}.get(name, zone.get('pattern', r'.+')), value):
                    detail['status'] = 'unrecognized'
                    log('metadata_unrecognized', field=name, value=value, confidence=detail['confidence'], crop=detail.get('crop'))
            except Exception as exc:
                result[name] = ''
                detail['error'] = str(exc)
                log('metadata_ocr_error', field=name, error=str(exc), crop=detail.get('crop'))
    result['metadata_details'] = details
    return result
