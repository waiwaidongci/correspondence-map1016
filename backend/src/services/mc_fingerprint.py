import hashlib,json
def mc_fingerprint(study,rows,columns,table):
 """Fingerprint of the active (zero-margin-dropped) table and its category metadata plus engine version.

 Row/column order changes do not matter; any count or label change changes the fingerprint and
 invalidates earlier conditional tests.
 """
 payload={'study':{k:study[k] for k in ('id','name','filename','description')},
  'rows':sorted(rows,key=lambda x:x['code']),'columns':sorted(columns,key=lambda x:x['code']),
  'table':sorted([[r['code'],c['code'],int(v)] for r,line in zip(rows,table) for c,v in zip(columns,line)]),
  'algorithm':'fixed-margin-conditional-monte-carlo-patefield-v1'}
 return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
