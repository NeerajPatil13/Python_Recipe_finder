# #urllib.request → URL se web page download karne ke liye
# urllib.parse → URL ke parts extract karne ya join karne ke liye
# urllib.robotparser → check karne ke liye ki site scraping allow karti hai ya nahi (robots.txt)
# json → JSON data (jaise recipe ka data) ko parse karne ke liye
# re → Regular expressions (HTML me text dhoondhne ke liye)
# html → HTML entities decode karne ke liye (&amp;, &quot; etc.)
# textwrap → text ko neatly wrap karne ke liye (console display me)
# time → delay dene ke liye (websites pe request spam na ho)
# sys → system level control (yahan mainly input/output handling me kaam aa sakta hai)
import urllib.request
import urllib.parse
import urllib.robotparser
import json 
import re 
import html
import textwrap 
import time

# Saara logic ek class me band hai — yeh object-oriented style ka code hai.
# Har ek function (“method”) class ke andar likha hai
class RecipeFinder:
    USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari"  #USER_AGENT → Browser jaisa behave karne ke liye (taaki site block na kare)
    SEARCH_URL = "https://duckduckgo.com/html/?q=" #SEARCH_URL → DuckDuckGo search page ka base URL
    TIMEOUT = 12 #TIMEOUT → Page download karte waqt maximum wait time (seconds)
    WRAP = 92 #WRAP → Console me text wrap karne ki width
    PREFERRED = ("allrecipes.com","bbcgoodfood.com","seriouseats.com","foodnetwork.com", 
                 "tasty.co","epicurious.com","thekitchn.com") #PREFERRED → Known recipe sites jinko preference dena hai

    def __init__(self, wrap=None, preferred=None):
        if wrap: self.WRAP = wrap
        if preferred: self.PREFERRED = tuple(preferred)#_init_-constructor - Agar user chahe to wrap aur preferred list change kar sakta hai.
        # Otherwise default values use hoti hain.

    def get(self, url):  #Web page download karne ke liye
        req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})
        with urllib.request.urlopen(req, timeout=self.TIMEOUT) as r:
            cs = r.headers.get_content_charset() or "utf-8"
            return r.read().decode(cs, "replace")#Yeh function:Browser jaisa request bhejta haResponse padhta haiHTML ko decode karke text return karta hai

    def can_fetch(self, url):#Yeh check karta hai ki website scraping allow karti hai ya nahi.
                            #Agar robots.txt unavailable ho to assume karta hai allowed hai.
        p = urllib.parse.urlsplit(url)
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"{p.scheme}://{p.netloc}/robots.txt")
        try:
            rp.read()
        except Exception:
            return True
        return rp.can_fetch("*", url)

    def search_duckduckgo(self, q, n=10):#DuckDuckGo pe search karta hai aur top n result URLs return karta hai.
        html_text = self.get(self.SEARCH_URL + urllib.parse.quote_plus(q))
        links = []
        for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"', html_text):#HTML se sab result links extract karta hai (regular expression se).
            href = html.unescape(m.group(1))
            if href.startswith("/"):
                href = urllib.parse.urljoin("https://duckduckgo.com", href)
            qs = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query)#DuckDuckGo links ke andar real URLs hoti hain (uddg param me) — unhe nikalta hai.
            #Phir duplicates hata kar n URLs return karta hai.
            links.append(qs.get("uddg",[href])[0])
        seen = set(); out=[]
        for u in links:
            if u not in seen:
                seen.add(u); out.append(u)
                if len(out) >= n: break
        return out

    def extract_jsonld(self, html_text):#HTML me se saare <script type="application/ld+json"> blocks nikalta hai aur unhe JSON me parse karta hai.
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

    def find_recipe_in_json(self, obj):#JSON me “recipe” dhoondhnaYeh recursive search karta hai aur jis dictionary me "@type": "Recipe" mile, use return karta hai.
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

    def norm_instructions(self, instr): #Recipe instructions ko normalize karta hai.#Recipe ke steps kabhi string hoti hain, kabhi list of dicts.
                                        #Yeh unhe ek clean list me convert karta hai (numbering ke saath).
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

    def scrape(self, url):#Ek URL se recipe scrape karta hai.#Sabse pehle check karta hai ki robots.txt allow karta hai ya nahi.#Phir page download karta hai aur JSON-LD blocks extract karta hai.
#Har block me recipe dhoondhta hai.#Agar mil jaye to uske name, ingredients, aur steps nikalta hai aur clean format me return karta hai.
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

    def prefer_sort(self, urls):#Known recipe domains ko preference deta hai aur URLs ko sort karta hai accordingly.
        def score(u):
            host = urllib.parse.urlsplit(u).netloc.lower()
            pref = any(host.endswith(d) for d in self.PREFERRED)
            return (1 if pref else 0, -len(u))
        return sorted(urls, key=score, reverse=True)

    def print_recipe(self, r):#to print recipe
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

    def run(self):#Main program loop
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
    RecipeFinder().run()#  main entry point function def print_recipe
