def extract_annotations(payload:dict)->dict:
    return {k:v for k,v in payload.items() if k.startswith(("vo_annotate.u.","vo_annotate.s.","vo_annotate.i."))}
