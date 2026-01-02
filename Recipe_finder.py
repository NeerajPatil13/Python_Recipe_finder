
import urllib.request
import urllib.parse
import urllib.robotparser
import json 
import re 
import html
import textwrap 
import time

class RecipeFinder:
    USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari"  
    SEARCH_URL = "https://duckduckgo.com/html/?q="
    TIMEOUT = 12 
    WRAP = 92 
    PREFERRED = ("allrecipes.com","bbcgoodfood.com","seriouseats.com","foodnetwork.com", 
                 "tasty.co","epicurious.com","thekitchn.com") 

    def __init__(self, wrap=None, preferred=None):
        if wrap: self.WRAP = wrap
        if preferred: self.PREFERRED = tuple(preferred)
     

    def get(self, url):  
        req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})
        with urllib.request.urlopen(req, timeout=self.TIMEOUT) as r:
            cs = r.headers.get_content_charset() or "utf-8"
            return r.read().decode(cs, "replace")

    def can_fetch(self, url):
        p = urllib.parse.urlsplit(url)
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"{p.scheme}://{p.netloc}/robots.txt")
        try:
            rp.read()
        except Exception:
            return True
        return rp.can_fetch("*", url)

    def search_duckduckgo(self, q, n=10):
        html_text = self.get(self.SEARCH_URL + urllib.parse.quote_plus(q))
        links = []
        for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"', html_text):
            href = html.unescape(m.group(1))
            if href.startswith("/"):
                href = urllib.parse.urljoin("https://duckduckgo.com", href)
            qs = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query)
            
            links.append(qs.get("uddg",[href])[0])
        seen = set(); out=[]
        for u in links:
            if u not in seen:
                seen.add(u); out.append(u)
                if len(out) >= n: break
        return out

    def extract_jsonld(self, html_text):
        blocks = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                            html_text, flags=re.S|re.I)
        objs=[]
        for b in blocks:
            s = html.unescape(b).strip()
            if not s: continue
            try:
                objs.append(json.loads(s))
            except Exception:
                try:
                    s2 = s.replace("\n"," ").strip()
                    if s2 and s2[0] != "[" and s2.count("{")>1:
                        s2 = "["+s2+"]"
                    objs.append(json.loads(s2))
                except Exception:
                    continue
        return objs

    def find_recipe_in_json(self, obj):
        stack = [obj]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                t = node.get("@type") or node.get("type") or ""
                types = t if isinstance(t, list) else [t]
                if any(str(x).lower()=="recipe" for x in types):
                    return node
                for v in node.values():
                    if isinstance(v,(dict,list)): stack.append(v)
            elif isinstance(node, list):
                for v in node:
                    if isinstance(v,(dict,list)): stack.append(v)
        return None

    def norm_instructions(self, instr):
        steps=[]
        if isinstance(instr,str):
            parts = re.split(r'(?:\r?\n){1,}|\.\s+(?=\d+\.)', instr)
            steps = [p.strip(" -•\t") for p in parts if p.strip()]
        elif isinstance(instr,list):
            for it in instr:
                if isinstance(it,str):
                    if it.strip(): steps.append(it.strip())
                elif isinstance(it,dict):
                    t = it.get("text") or it.get("name") or ""
                    if t.strip(): steps.append(t.strip())
        return steps

    def scrape(self, url):
        if not self.can_fetch(url): return None, f"robots disallow {url}"
        try:
            page = self.get(url)
        except Exception as e:
            return None, f"fetch failed: {e}"
        for block in self.extract_jsonld(page):
            rec = self.find_recipe_in_json(block)
            if not rec:
                rec = (block.get("mainEntity") if isinstance(block, dict) else None)
            if not rec: continue
            name = (rec.get("name") or "").strip()
            ingr = rec.get("recipeIngredient") or rec.get("ingredients") or []
            instr = rec.get("recipeInstructions") or rec.get("instructions") or []
            steps = self.norm_instructions(instr)
            ingr = [html.unescape(i).strip() for i in ingr if isinstance(i,str) and i.strip()]
            steps = [html.unescape(s).strip() for s in steps if s.strip()]
            if name or ingr or steps:
                return {"name": name or "Recipe", "url": url, "ingredients": ingr, "steps": steps}, None
        return None, "no recipe found"

    def prefer_sort(self, urls):
        def score(u):
            host = urllib.parse.urlsplit(u).netloc.lower()
            pref = any(host.endswith(d) for d in self.PREFERRED)
            return (1 if pref else 0, -len(u))
        return sorted(urls, key=score, reverse=True)

    def print_recipe(self, r)
        title = r.get("name","Recipe")
        print("\n"+title); print("="*max(len(title),16))
        if r.get("url"): print(r["url"]+"\n")
        if r.get("ingredients"):
            print("Ingredients"); print("-----------")
            for i in r["ingredients"]:
                print(textwrap.fill(f"- {i}", width=self.WRAP))
            print()
        if r.get("steps"):
            print("Instructions"); print("------------")
            for n,s in enumerate(r["steps"],1):
                print(textwrap.fill(f"{n}. {s}", width=self.WRAP))
            print()

    def run(self):
        print("Kya khaogeeeee — type a dish name, or 'exit' to quit.")
        while True:
            try:
                dish = input("\nDish ka name: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!"); return
            if not dish:
                print("Please enter a dish name."); continue
            if dish.lower() in {"exit","quit","q"}:
                print("Goodbye!"); break
            q = f"{dish} recipe"
            print("Searching:", q)
            try:
                urls = self.search_duckduckgo(q, n=12)
            except Exception:
                print("Search failed."); continue
            if not urls:
                print("No results."); continue
            urls = self.prefer_sort(urls)
            found=None; errors=[]
            for idx,u in enumerate(urls,1):
                print(f"→ Checking {idx}: {u}")
                rec, err = self.scrape(u)
                if rec:
                    found=rec; break
                errors.append(err or "unknown")
                time.sleep(0.6)
            if found:
                self.print_recipe(found)
            else:
                print("\nCouldn't extract a recipe from top results.")
                if errors:
                    for e in errors[:3]:
                        print(" -", e)

if __name__ == "__main__":
    RecipeFinder().run()

