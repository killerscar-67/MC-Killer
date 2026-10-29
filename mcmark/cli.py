import argparse
import json
import logging
from pathlib import Path
from .core import validate, grade, export


def run(inputs, config, output, corrections=None):
    from .vision import pages, align, detect, metadata
    import cv2
    from .review import save_question_crop, refresh_review, apply_corrections, write_review
    events,results = [],[]
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    (out/'review').mkdir(exist_ok=True)
    seen = {}
    sheet_sequence = 0
    files = sorted({p.resolve() for source in inputs for p in (Path(source).rglob('*') if Path(source).is_dir() else [Path(source)]) if p.suffix.lower() in {'.png','.jpg','.jpeg','.tif','.tiff','.bmp','.pdf'}})
    if not files:
        raise ValueError('No supported input files found')
    for path in files:
        page_number = 0
        def log(kind, **extra):
            event = dict(file=str(path),page=page_number,kind=kind,**extra)
            events.append(event)
            logging.warning('%s', json.dumps(event))
        try:
            for page_number, raw in pages(path):
                sheet_sequence += 1
                start = len(events)
                try:
                    gray = align(raw, config)
                    profile = metadata(gray, config, log, out/'review'/'metadata', f'{sheet_sequence:05d}')
                    responses = []
                    for q in config['questions']:
                        reading = detect(gray,q,config)
                        responses.append(reading)
                        if reading['review_reasons']:
                            reading['review_crop'] = save_question_crop(gray,q,out/'review'/'questions'/f'{sheet_sequence:05d}-q{len(responses):03d}.png')
                            log('question_review', question=q['id'], **reading)
                    result = dict(file=str(path),page=page_number,**profile,**grade(responses,config))
                    result['sheet_review_issues'] = [e['kind'] for e in events[start:] if e['kind'] != 'question_review']
                    identity = (profile.get('class'),profile.get('student_id'))
                    if all(identity) and not any('?' in value for value in identity):
                        if identity in seen:
                            log('duplicate_identity', identity=identity)
                            result['sheet_review_issues'].append('duplicate_identity')
                            seen[identity]['sheet_review_issues'].append('duplicate_identity')
                            refresh_review(seen[identity])
                        else:
                            seen[identity] = result
                    refresh_review(result)
                    results.append(result)
                    # Save registered evidence for review, including filled responses.
                    preview = cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
                    for q,a in zip(config['questions'],responses):
                        for label,center in zip(q['labels'],q['centers']):
                            if label in a['selected']:
                                cv2.circle(preview,tuple(map(int,center)),int(q.get('radius',config.get('radius',10)))+3,(0,0,255),2)
                    cv2.imwrite(str(out/'review'/f'{len(results):05d}.png'),preview)
                    logging.info('Processed %s page %d: %.2f%%',path.name,page_number,result['percent'])
                except Exception as exc:
                    log('sheet_error', error=str(exc))
        except Exception as exc:
            log('file_error', error=str(exc))
    if corrections:
        apply_corrections(results,config,corrections)
    if config.get('identity_mode')=='roster':
        from .roster import assign_roster
        # Never compress identities around failed pages. A failed batch cannot
        # publish order-based assignments or be finalized.
        if any(e['kind'] in {'sheet_error','file_error'} for e in events):
            raise ValueError('Some sheets failed processing; roster identities were not assigned.')
        assign_roster(results,config)
    export(results,config,out,events)
    write_review(results,out)
    return 2 if any(e['kind'] in {'sheet_error','file_error'} for e in events) else 0


def main():
    parser = argparse.ArgumentParser(description='Digitize and mark MCQ sheets')
    parser.add_argument('inputs', nargs='+', help='Image/PDF files or folders (recursive)')
    parser.add_argument('--config', required=True, help='JSON layout, answer key, and scoring')
    parser.add_argument('--output', default='output')
    parser.add_argument('--key', help='JSON object mapping question IDs to correct options; only listed questions are graded')
    parser.add_argument('--corrections', help='Teacher decisions from an edited review_queue.csv')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    try:
        config = json.loads(Path(args.config).read_text())
        if args.key:
            key = json.loads(Path(args.key).read_text())
            if not isinstance(key, dict) or not key:
                raise ValueError('Answer key must be a nonempty JSON object')
            known = {str(q['id']) for q in config['questions']}
            if set(key)-known:
                raise ValueError('Answer key contains question IDs absent from the layout')
            config['questions'] = [{**q, 'answer':key[str(q['id'])]} for q in config['questions'] if str(q['id']) in key]
        if any(q.get('answer') is None for q in config['questions']):
            raise ValueError('This layout needs an answer key. Use --key answers.json (for example {"1":"A","2":"C"})')
        if config.get('template_image'):
            config['template_image'] = str((Path(args.config).resolve().parent / config['template_image']).resolve())
        config = validate(config)
        raise SystemExit(run(args.inputs,config,args.output,corrections=args.corrections))
    except (ValueError,KeyError,TypeError,OSError) as exc:
        parser.error(str(exc))

if __name__ == '__main__':
    main()
