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
    raw_count = int(np.count_nonzero(ink[outside]))
    # Residual printed borders/letters are not student ink. Remove their
    # one-pixel registration halo before counting detached spill.
    printed=cv2.dilate((reference<200).astype(np.uint8),np.ones((3,3),np.uint8))
    clean=(ink>0)&(printed==0)
    count = int(np.count_nonzero(clean[outside]))
    # Bridge at most a one-pixel gap for connectivity only; never add those
    # dilated pixels to optical density or ink counts.
    _,components=cv2.connectedComponents(cv2.dilate(clean.astype(np.uint8),np.ones((3,3),np.uint8)),connectivity=8)
    core=(abs(xx-x)<=bw/2)&(abs(yy-y)<=bh/2)
    linked_ids=np.unique(components[core & clean]);linked_ids=linked_ids[linked_ids!=0]
    attached=int(np.count_nonzero(clean & outside & np.isin(components,linked_ids)))
    slopes = set()
    lines = cv2.HoughLinesP(ink,1,np.pi/180,threshold=8,minLineLength=12,maxLineGap=3)
    if lines is not None:
        for x1,y1,x2,y2 in lines.reshape(-1,4):
            dx,dy = int(x2-x1),int(y2-y1)
            if dx and .35 <= abs(dy/dx) <= 3 and min(y1,y2)+top < y-bh/2-2 and max(y1,y2)+top > y+bh/2+2:
                slopes.add(1 if dx*dy>0 else -1)
    return {'outside_ink_pixels':count,'raw_outside_ink_pixels':raw_count,
            'attached_spill_pixels':attached,'detached_spill_pixels':count-attached,
            'cross_suspected':len(slopes)==2}


def diagonal_support(ink, center):
    """Require straight ink through both sides, not curved arc tangents."""
    x,y=center
    supports=[]
    for sign in (-1,1):
        best=0.0
        for slope in (.6,.8,1.0,1.2):
            sides=[]
            for side in (-1,1):
                hits=[]
                for distance in range(3,8):
                    px=round(x+side*distance);py=round(y+sign*slope*side*distance)
                    region=ink[max(0,py-1):py+2,max(0,px-1):px+2]
                    hits.append(bool(region.size and np.any(region)))
                sides.append(sum(hits)/len(hits))
            best=max(best,min(sides))
        supports.append(best)
    return supports


def stroke_features(gray, template, grid, center, config):
    """Template-subtracted candidate strokes; cancellation is always provisional."""
    x,y = center
    bw,bh = grid['sample_box']
    rx,ry = int(bw/2+7),int(bh/2+8)
    left,top = max(0,round(x)-rx),max(0,round(y)-ry)
    right,bottom = min(gray.shape[1],round(x)+rx+1),min(gray.shape[0],round(y)+ry+1)
    patch = gray[top:bottom,left:right]
    ref = template[top:bottom,left:right]
    # Ignore printed ink and its one-pixel registration halo.
    printed = cv2.dilate((ref < 200).astype(np.uint8),np.ones((3,3),np.uint8))
    foreground_limit=min(200,float(np.percentile(patch,90))-30)
    ink = ((ref.astype(np.int16)-patch.astype(np.int16)>40) & (patch<foreground_limit) & (printed==0)).astype(np.uint8)
    yy,xx=np.ogrid[top:bottom,left:right]
    core=(abs(xx-x)<=bw/2+1)&(abs(yy-y)<=bh/2+2)
    inner=ink*core.astype(np.uint8)
    count,_,stats,_=cv2.connectedComponentsWithStats(inner,8)
    components=[s for s in stats[1:count] if s[cv2.CC_STAT_AREA]>=3]
    area=max((int(s[cv2.CC_STAT_AREA]) for s in components),default=0)
    span=max((int(max(s[cv2.CC_STAT_WIDTH],s[cv2.CC_STAT_HEIGHT])) for s in components),default=0)
    thin=area>=5 and span>=5
    # Fit opposite diagonals near the centre, rather than demanding both
    # strokes extend far above and below a box. Dense fills alone are not Xs.
    line_ink=((ref.astype(np.int16)-patch.astype(np.int16)>40)&(patch<foreground_limit)).astype(np.uint8)*255
    lines=cv2.HoughLinesP(line_ink,1,np.pi/180,threshold=4,minLineLength=6,maxLineGap=4)
    outer_ink=line_ink.copy()
    outer_ink[(abs(xx-x)<=bw/2)&(abs(yy-y)<=bh/2+1)]=0
    outer_lines=cv2.HoughLinesP(outer_ink,1,np.pi/180,threshold=4,minLineLength=7,maxLineGap=7)
    if outer_lines is not None:
        lines=outer_lines if lines is None else np.concatenate((lines,outer_lines))
    diagonals=[]
    if lines is not None:
        for a,b,c,d in lines.reshape(-1,4):
            dx,dy=int(c-a),int(d-b)
            if not dx or not .45<=abs(dy/dx)<=2.5: continue
            a,b,c,d=float(a+left),float(b+top),float(c+left),float(d+top)
            if min(a,c)>x+3 or max(a,c)<x-3: continue
            if min(b,d)>y+2 or max(b,d)<y-2: continue
            diagonals.append((a,b,c,d))
    cross=False
    for a,b,c,d in diagonals:
        for e,f,g,h in diagonals:
            if (c-a)*(d-b)*(g-e)*(h-f)>=0: continue
            det=(a-c)*(f-h)-(b-d)*(e-g)
            if abs(det)<1e-6: continue
            ix=((a*d-b*c)*(e-g)-(a-c)*(e*h-f*g))/det
            iy=((a*d-b*c)*(f-h)-(b-d)*(e*h-f*g))/det
            if abs(ix-x)>4 or abs(iy-y)>4: continue
            if not all(min(u,v)-1<=z<=max(u,v)+1 for u,v,z in ((a,c,ix),(b,d,iy),(e,g,ix),(f,h,iy))): continue
            # Require diagonal evidence outside the narrow density sample.
            if max(abs(b-y),abs(d-y))>=bh/2+2 and max(abs(f-y),abs(h-y))>=bh/2+2:
                cross=True
    # Dense fill can hide line segments. Look for all four diagonal arms
    # beyond the fill core; a single slash or a rectangle cannot satisfy this.
    arms=[]
    for sign in (-1,1):
        supported=False
        for slope in (.6,.8,1.0,1.2):
            band=(abs((yy-y)-sign*slope*(xx-x))<=1.5)&(abs(yy-y)>=bh/2+2)&(abs(xx-x)<=bw/2+3)
            if all(np.count_nonzero(line_ink[band & ((xx-x)*side>=3)])>=2 for side in (-1,1)):
                supported=True
        arms.append(supported)
    support=diagonal_support(line_ink,(x-left,y-top))
    straight=[value>=.8 for value in support]
    cross=(cross or all(arms)) and all(arms) and all(straight)
    # Measure diagonal arms beyond the filled box, using print-masked ink.
    # Dense rectangles can satisfy short diagonal tests inside their body.
    far_arms=[]
    for sx,sy in ((-1,-1),(-1,1),(1,-1),(1,1)):
        region=(sx*(xx-x)>=bw/2-2)&(sy*(yy-y)>=bh/2+4)
        far_arms.append(int(np.count_nonzero(ink[region])))
    fill_core=(abs(xx-x)<=bw/2-2)&(abs(yy-y)<=bh/2)
    fill_coverage=float(np.mean(line_ink[fill_core]>0)) if np.any(fill_core) else 0.0
    beyond_body=(abs(yy-y)>=bh/2+4)|(abs(xx-x)>=bw/2+4)
    far_pixels=int(np.count_nonzero(ink[beyond_body]))
    compact_fill=fill_coverage>=.80 and far_pixels<=2
    return {'new_ink_pixels':int(inner.sum()),'stroke_area':area,'stroke_span':span,
            'fill_core_coverage':fill_coverage,'far_arm_pixels':far_arms,
            'beyond_fill_body_pixels':far_pixels,'compact_fill':bool(compact_fill),
            'thin_candidate':bool(thin),'diagonal_clue':bool(any(arms) and any(straight)), 'compact_cross_suspected':bool(cross),
            'straight_diagonal_support':support}


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
        template = config['_template_array'] if '_template_array' in config else load_template(config['template_image'])
        if template is None or template.shape != (h, w):
            raise ValueError('Template image missing or has incorrect dimensions')
        orb = cv2.ORB_create(nfeatures=7000)
        source_keys, source_desc = orb.detectAndCompute(scaled, None)
        target_keys, target_desc = orb.detectAndCompute(template, None)
        if source_desc is None or target_desc is None:
            raise ValueError('Insufficient features to register sheet')
        pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(source_desc, target_desc, k=2)
        # Repeated answer rows can produce a high-inlier homography supported
        # only by the header. Retry stricter descriptor matches, retaining all
        # geometric coverage and distortion checks for every hypothesis.
        failure='Sheet does not match the configured template'
        for ratio in (.7,.6):
            matches=[m for pair in pairs if len(pair)==2 for m,n in [pair] if m.distance<ratio*n.distance]
            if len(matches)<20: continue
            source=np.float32([source_keys[m.queryIdx].pt for m in matches])
            target=np.float32([target_keys[m.trainIdx].pt for m in matches])
            matrix,inliers=cv2.findHomography(source,target,cv2.RANSAC,3)
            if matrix is None or int(inliers.sum())<20 or float(inliers.mean())<.4:
                failure='Unreliable template registration; manual review required'
                continue
            matched=target[inliers.ravel().astype(bool)]
            if np.ptp(matched[:,0])<w*.35 or np.ptp(matched[:,1])<h*.35:
                failure='Registration features do not cover enough of the sheet'
                continue
            corners=np.float32([[[0,0],[w,0],[w,h],[0,h]]])
            projected=cv2.perspectiveTransform(corners,matrix)[0]
            if np.max(np.linalg.norm(projected-corners[0],axis=1))>min(w,h)*.2:
                failure='Sheet rotation/crop exceeds supported registration range'
                continue
            return cv2.warpPerspective(scaled,matrix,(w,h),borderValue=255)
        raise ValueError(failure)
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


def apply_review_policy(reading, config):
    """Accept isolated, well-registered strokes; preserve all ambiguous evidence."""
    reading['review_policy'] = 'balanced-v3'
    reading['original_review_reasons'] = list(reading['review_reasons'])
    if config.get('review_policy') == 'conservative':
        reading['review_policy'] = 'conservative'
        return reading
    selected = reading['selected']
    reasons = set(reading['review_reasons'])
    # Never suppress competing ink, cancellation clues or failed registration.
    if len(selected) != 1 or reasons - {'uncertain_density', 'faint_or_partial_mark', 'thin_stroke_candidate','stray_ink_or_cancellation','possible_cancellation_stroke'}:
        return reading
    label = selected[0]
    clues = reading.get('mark_clues', {})
    mark = clues.get(label, {})
    compact_fill=bool(mark.get('compact_fill'))
    if 'possible_cancellation_stroke' in reasons and not compact_fill:return reading
    minor_spill=('stray_ink_or_cancellation' in reasons)
    # A verified compact fill can have connected pen spill, but detached
    # marks retain the smaller limit. This never overrides cross evidence.
    spill_limit=24 if compact_fill and mark.get('detached_spill_pixels',float('inf'))<=2 else 16
    if minor_spill and (mark.get('outside_ink_pixels',float('inf'))>spill_limit
        or any(c.get('outside_ink_pixels',float('inf'))>4 for option,c in clues.items() if option!=label)):
        return reading
    if (reading.get('alignment_score', 0) >= .70
        and reading['densities'][label] >= .08
        and mark.get('stroke_area', 0) >= 10
        and mark.get('stroke_span', 0) >= 7
        and not any(c.get('cross_suspected') or (c.get('diagonal_clue') and (option!=label or not compact_fill)) for option,c in clues.items())
        and all(c.get('new_ink_pixels', 0) <= 2 for option,c in clues.items() if option != label)):
        reading['review_reasons'] = []
        reading['auto_accept_reason'] = ('isolated_compact_fill' if 'possible_cancellation_stroke' in reasons
                                        else 'isolated_mark_minor_spill' if minor_spill else 'isolated_registered_stroke')
    return reading


def detect(gray, grid, config):
    # Global homography can leave a few pixels of local drift. Register each
    # printed question row before sampling a four-pixel-high box interior.
    if grid.get('sample_box') and config.get('template_image') and not config.get('_local_aligned'):
        reference=load_template(config['template_image'])
        xs,ys=zip(*grid['centers']);pad=5
        left=max(pad,int(min(xs))-23);top=max(pad,int(min(ys))-20)
        right=min(gray.shape[1]-pad,int(max(xs))+24);bottom=min(gray.shape[0]-pad,int(max(ys))+21)
        target=reference[top:bottom,left:right]
        window=gray[top-pad:bottom+pad,left-pad:right+pad]
        match=cv2.matchTemplate(window,target,cv2.TM_CCOEFF_NORMED)
        _,score,_,position=cv2.minMaxLoc(match);dx,dy=position[0]-pad,position[1]-pad
        initial={'offset':[dx,dy],'score':float(score),'radius':pad}
        # Retry low-score interior matches too: the true row may lie outside
        # the first window. Fourteen pixels stays below half the Delia option
        # and row spacing, avoiding a jump to the next option/question.
        # The larger search requires stronger evidence than ordinary sampling.
        for retry_pad in (9,14):
            if score>=.60 and abs(dx)<pad and abs(dy)<pad:break
            if top>=retry_pad and left>=retry_pad and right+retry_pad<=gray.shape[1] and bottom+retry_pad<=gray.shape[0]:
                retry_window=gray[top-retry_pad:bottom+retry_pad,left-retry_pad:right+retry_pad]
                retry=cv2.matchTemplate(retry_window,target,cv2.TM_CCOEFF_NORMED)
                _,retry_score,_,retry_position=cv2.minMaxLoc(retry)
                retry_dx,retry_dy=retry_position[0]-retry_pad,retry_position[1]-retry_pad
                # Equal locations may differ by floating-point roundoff in
                # differently sized OpenCV windows; don't reject that retry.
                tolerance=.001 if (retry_dx,retry_dy)==(dx,dy) else 0
                if retry_score>=max(.60,score-tolerance):
                    window=retry_window;pad=retry_pad;score=retry_score;position=retry_position
                    dx,dy=retry_dx,retry_dy
        patch=window[position[1]:position[1]+target.shape[0],position[0]:position[0]+target.shape[1]]
        local_grid={**grid,'centers':[[x-left,y-top] for x,y in grid['centers']]}
        if score<.45 or abs(dx)==pad or abs(dy)==pad:
            reading=detect(gray,grid,{**config,'_local_aligned':True,'_disable_strokes':True})
            reading['review_reasons'].append('uncertain_local_alignment')
        else:
            reading=detect(patch,local_grid,{**config,'_local_aligned':True,'_template_array':target})
        reading['local_offset']=[dx,dy];reading['alignment_score']=float(score);reading['local_search_radius']=pad
        reading['alignment_version']='row-bounded-v2'
        if pad>5 and 'uncertain_local_alignment' not in reading['review_reasons']:
            reading['alignment_recovery']={'initial':initial,'offset':[dx,dy],'radius':pad,'score':float(score)}
        return apply_review_policy(reading,config)
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
        template = config['_template_array'] if '_template_array' in config else load_template(config['template_image'])
        for label,center in zip(grid['labels'],grid['centers']):
            clue = surrounding_ink(gray,template,grid,center,config)
            clues[label] = clue
            if clue['cross_suspected']:
                reasons.append('possible_cross_out')
            elif clue['outside_ink_pixels'] >= config.get('outside_ink_min_pixels', 12):
                reasons.append('stray_ink_or_cancellation')
    raw_selected=list(selected)
    thin_candidates=[]
    if grid.get('sample_box') and config.get('template_image') and not config.get('_disable_strokes'):
        template=config['_template_array'] if '_template_array' in config else load_template(config['template_image'])
        for label,center in zip(grid['labels'],grid['centers']):
            feature=stroke_features(gray,template,grid,center,config)
            clue=clues.setdefault(label,{})
            clue.update(feature)
            clue['cross_suspected']=bool(feature['compact_cross_suspected'] or (clue.get('cross_suspected') and clue.get('raw_outside_ink_pixels',clue.get('outside_ink_pixels',0))>=30))
            if clue['cross_suspected']:
                reasons.append('possible_cross_out')
            elif feature['diagonal_clue']:
                reasons.append('possible_cancellation_stroke')
            partial=(densities[label]>=.12 and feature['new_ink_pixels']>=3 and feature['stroke_area']>=3 and feature['stroke_span']>=3)
            clue['partial_density_candidate']=bool(partial)
            if label not in selected and (feature['thin_candidate'] or partial or (clue['cross_suspected'] and feature['new_ink_pixels']>=5)):
                thin_candidates.append(label)
                reasons.append('thin_stroke_candidate')
            clue['state']='likely_cancelled' if clue['cross_suspected'] else 'ambiguous' if feature['diagonal_clue'] else 'active_mark' if label in selected else 'ambiguous' if feature['new_ink_pixels'] else 'blank'
    if clues and not config.get('_disable_strokes'):
        reasons=[r for r in reasons if r!='possible_cross_out']
        if any(c.get('cross_suspected') for c in clues.values()): reasons.append('possible_cross_out')
    if len(thin_candidates)==1:
        selected.append(thin_candidates[0])
        clues[thin_candidates[0]]['state']='ambiguous' if clues[thin_candidates[0]]['diagonal_clue'] else 'active_mark'
    elif thin_candidates:
        reasons.append('ambiguous_thin_marks')
    if len(thin_candidates)==1:
        reasons=[r for r in reasons if r not in ('blank','multiple')]
        if len(selected)>1: reasons.append('multiple')
    crossed = [label for label,clue in clues.items() if clue.get('cross_suspected')]
    remaining = [label for label in selected if label not in crossed]
    for label in crossed:
        clues[label]['state']='likely_cancelled' if remaining else 'ambiguous'
    extended_diagonals=[label for label in selected if clues.get(label,{}).get('diagonal_clue')
        and clues[label].get('raw_outside_ink_pixels',clues[label].get('outside_ink_pixels',0))>=20
        and all(v>=.8 for v in clues[label].get('straight_diagonal_support',[0,0]))]
    cancellation_candidates=set(crossed)|set(extended_diagonals)
    suggestion_remaining=[label for label in selected if label not in cancellation_candidates]
    suggestion=(suggestion_remaining if cancellation_candidates and len(selected)>1 and len(suggestion_remaining)==1 and len(thin_candidates)<=1
        else remaining if (crossed or len(thin_candidates)==1) and len(remaining)==1 and len(thin_candidates)<=1 else None)
    return {'selected':selected, 'raw_selected':raw_selected, 'densities':densities,
            'uncertain':uncertain, 'mark_clues':clues, 'review_reasons':list(dict.fromkeys(reasons)),
            'detector_version':'stroke-v2.3', 'thin_candidates':thin_candidates,
            'suggested_selected':suggestion, 'suggestion_basis':'extended_diagonal' if extended_diagonals and suggestion else 'cross_or_thin' if suggestion else None}



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
            if config.get('identity_mode')=='roster':
                result[name]=''
                detail.update(status='image_only',raw_text='',identity_source='roster_order')
                continue
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
