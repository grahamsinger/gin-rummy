// Paste into the browser console on a page of the running app to compare the
// computed style of every element under two builds of the stylesheets.
//
// Setup: keep a copy of the old page and stylesheet in web/static (for example
//   git show <old>:gin_rummy/web/static/style.css > gin_rummy/web/static/style-old.css
//   git show <old>:gin_rummy/web/static/index.html | sed 's|/static/style.css|/static/style-old.css|' > gin_rummy/web/static/old-index.html
// ), then run cssComputedDiff('/static/old-index.html', '/') here. Both pages
// load in same-size iframes in this session, so dynamic content matches.
// A result of `differing: 0` means no element's computed style changed.
// Delete the old-* copies afterwards; they are not part of the app.
async function cssComputedDiff(oldUrl, newUrl) {
    async function load(url) {
        const f = document.createElement('iframe');
        f.style.cssText = `position:fixed;left:0;top:0;width:${window.innerWidth}px;height:${window.innerHeight}px;border:0;opacity:0.01`;
        document.body.appendChild(f);
        await new Promise(res => { f.onload = res; f.src = url; });
        await new Promise(r => setTimeout(r, 2500));
        return f;
    }
    function snapshot(win) {
        return [...win.document.querySelectorAll('body *')].map(el => {
            const cs = win.getComputedStyle(el);
            const o = {};
            // custom properties (--x) inherit onto every element; only rendered values matter
            for (const p of cs) if (!p.startsWith('--')) o[p] = cs.getPropertyValue(p);
            return { key: `${el.tagName}#${el.id}.${el.className}`, o };
        });
    }
    const a = await load(oldUrl);
    const b = await load(newUrl);
    const sa = snapshot(a.contentWindow);
    const sb = snapshot(b.contentWindow);
    const diffs = [];
    sb.forEach((el, i) => {
        const o = sa[i];
        if (!o || o.key !== el.key) { diffs.push({ i, key: el.key, oldKey: o && o.key }); return; }
        for (const p in el.o) if (o.o[p] !== el.o[p]) diffs.push({ key: el.key, p, old: o.o[p], now: el.o[p] });
    });
    a.remove();
    b.remove();
    return { oldElements: sa.length, newElements: sb.length, differing: diffs.length, sample: diffs.slice(0, 20) };
}
