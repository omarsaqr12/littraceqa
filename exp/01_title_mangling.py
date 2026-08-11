import json, re, collections
M=[json.loads(l) for l in open('data/paper_metadata.jsonl')]
pat=re.compile(r'\b[A-Z] [a-z]')
mangled=[m for m in M if pat.search(m['title'])]
print(f"titles with ' X ' mangling pattern: {len(mangled)}/{len(M)} = {len(mangled)/len(M):.1%}")
for m in mangled[:12]: print("   ", m['title'][:90])
print("\nHTML entities in titles:", sum(1 for m in M if '&' in m['title'] and ';' in m['title']))
for m in M:
    if '&#' in m['title']: print("   ", m['title'][:90]); break
# does abstract have same mangling?
am=[m for m in M if m.get('abstract') and pat.search(m['abstract'][:300])]
print("\nabstracts with mangling (first 300 chars):", len(am))
