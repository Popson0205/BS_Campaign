from flask import Flask, request, jsonify, send_file, render_template_string
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io, os, traceback

app = Flask(__name__)

T2_PATH = os.path.join(os.path.dirname(__file__), 'template004.png')  # 1402x1122

# ── Photo slot (rounded rect, green gradient border) ──
# Border: x=263..813, y=82..787
# We use a 12px inset from the border on all sides so photo never touches it
T2_PHOTO_X1, T2_PHOTO_Y1 = 278,  96
T2_PHOTO_X2, T2_PHOTO_Y2 = 800, 772
T2_PHOTO_W = T2_PHOTO_X2 - T2_PHOTO_X1   # 522
T2_PHOTO_H = T2_PHOTO_Y2 - T2_PHOTO_Y1   # 676

# ── Courtesy name box ──
# Red "Courtesy:" italic label: y=834..844
# Clean white write zone: y=847..863  (centre y=855)
# Horizontal: x=309 (dotted left border) .. x=820 (right edge)  centre x=564
T2_NAME_CX = 536
T2_NAME_Y  = 884

DESIGNS = [
    {"id":1,"label":"Classic Green", "swatch":"linear-gradient(135deg,#1a6b2a,#1a3a6b)","overlay":None},
    {"id":2,"label":"Royal Blue",    "swatch":"linear-gradient(135deg,#1a3a8b,#0a1f5c)","overlay":(0,20,80,50)},
    {"id":3,"label":"Gold & Black",  "swatch":"linear-gradient(135deg,#8b6914,#2c1f00)","overlay":(50,25,0,40)},
    {"id":4,"label":"Emerald Pride", "swatch":"linear-gradient(135deg,#0a6b2a,#004d1a)","overlay":(0,55,20,40)},
    {"id":5,"label":"Crimson Power", "swatch":"linear-gradient(135deg,#8b1a1a,#4d0000)","overlay":(90,0,0,40)},
]

def get_font(size, bold=False):
    paths = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf' if bold else '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
    ]
    for p in paths:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except: pass
    return ImageFont.load_default()

def fit_and_paste(tpl, photo_bytes, x1, y1, x2, y2, radius=30):
    """Contain-fit photo centred in box with 8px padding — never touches the border."""
    pad = 8
    box_w = x2 - x1 - pad * 2
    box_h = y2 - y1 - pad * 2

    user_img = Image.open(io.BytesIO(photo_bytes)).convert("RGBA")
    uw, uh = user_img.size

    # Contain-fit: scale so entire photo fits inside the box
    scale = min(box_w / uw, box_h / uh)
    fit_w = int(uw * scale)
    fit_h = int(uh * scale)
    user_img = user_img.resize((fit_w, fit_h), Image.LANCZOS)

    # Centre within padded box
    ox = pad + (box_w - fit_w) // 2
    oy = pad + (box_h - fit_h) // 2

    # Rounded rect mask
    mask = Image.new("L", (fit_w, fit_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, fit_w, fit_h), radius=radius, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=1))
    user_img.putalpha(mask)

    tpl.paste(user_img, (x1 + ox, y1 + oy), user_img)
    return tpl

def draw_name(tpl, name):
    """Always wrap name to two centred lines inside the courtesy box.
    Box: x=373..809 (w=436), y=868..930 (h=62).
    Splits at the word boundary closest to the middle of the string.
    """
    if not name:
        return tpl
    draw = ImageDraw.Draw(tpl)

    BOX_X1, BOX_X2 = 373, 809
    BOX_Y1, BOX_Y2 = 868, 930
    box_w  = BOX_X2 - BOX_X1   # 436
    box_h  = BOX_Y2 - BOX_Y1   # 62
    box_cx = (BOX_X1 + BOX_X2) // 2   # 591
    box_cy = (BOX_Y1 + BOX_Y2) // 2   # 899

    def measure(text, font):
        bb = draw.textbbox((0, 0), text, font=font)
        return bb[2] - bb[0], bb[3] - bb[1]

    def best_split(words):
        """Split word list at the boundary closest to the string midpoint."""
        mid = len(' '.join(words)) // 2
        pos = 0
        best_i, best_dist = 1, float('inf')
        for i in range(1, len(words)):
            pos += len(words[i-1]) + 1
            dist = abs(pos - mid)
            if dist < best_dist:
                best_dist = dist
                best_i = i
        return ' '.join(words[:best_i]), ' '.join(words[best_i:])

    words = name.split()

    # Try two-line layout at decreasing font sizes
    result = None
    for sz in [28, 24, 22, 20, 18, 16, 14]:
        f = get_font(sz, bold=True)
        if len(words) >= 2:
            l1, l2 = best_split(words)
        else:
            l1, l2 = name, ''
        w1, h1 = measure(l1, f)
        w2, h2 = (measure(l2, f) if l2 else (0, 0))
        line_gap = 6
        total_h = h1 + (line_gap + h2 if l2 else 0)
        if w1 <= box_w - 10 and (not l2 or w2 <= box_w - 10) and total_h <= box_h - 4:
            result = (f, [l1, l2] if l2 else [l1])
            break

    if not result:
        result = (get_font(13, bold=True), [name])

    font, lines = result
    line_gap = 6
    line_sizes = [measure(l, font) for l in lines]
    total_h = sum(h for _, h in line_sizes) + line_gap * (len(lines) - 1)
    y = box_cy - total_h // 2

    for line, (lw, lh) in zip(lines, line_sizes):
        x = box_cx - lw // 2
        draw.text((x + 1, y + 1), line, font=font, fill=(160, 140, 60, 120))
        draw.text((x, y), line, font=font, fill=(10, 55, 15))
        y += lh + line_gap

    return tpl
def composite_t2(photo_bytes, name, design_id):
    design = next(d for d in DESIGNS if d["id"] == design_id)
    tpl = Image.open(T2_PATH).convert("RGBA")
    if design["overlay"]:
        r, g, b, a = design["overlay"]
        tpl = Image.alpha_composite(tpl, Image.new("RGBA", tpl.size, (r, g, b, a)))

    tpl = fit_and_paste(tpl, photo_bytes, T2_PHOTO_X1, T2_PHOTO_Y1, T2_PHOTO_X2, T2_PHOTO_Y2, radius=30)
    tpl = draw_name(tpl, name)

    buf = io.BytesIO()
    tpl.convert("RGB").save(buf, format="JPEG", quality=93)
    buf.seek(0)
    return buf


HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BSE4 Initiative — Support Frame Generator</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',sans-serif;background:#f0f2f5;color:#111827;min-height:100vh;padding:24px 16px 48px}
.container{max-width:960px;margin:0 auto}
.hero{text-align:center;margin-bottom:22px}
.hero-badge{display:inline-flex;align-items:center;gap:6px;background:linear-gradient(135deg,#1a3a6b,#0f2444);color:#d4af37;font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;padding:6px 16px;border-radius:100px;margin-bottom:10px}
.hero h1{font-size:clamp(20px,5vw,28px);font-weight:800;color:#0f172a;margin-bottom:5px}
.hero p{font-size:14px;color:#4b5563;max-width:460px;margin:0 auto}
.design-tabs{display:flex;gap:7px;flex-wrap:wrap;justify-content:center;margin-bottom:18px}
.design-tab{display:flex;align-items:center;gap:7px;padding:7px 13px;border-radius:100px;border:2px solid rgba(0,0,0,0.1);background:white;cursor:pointer;font-size:12px;font-weight:600;color:#374151;transition:all .15s;font-family:inherit}
.design-tab:hover{border-color:#1a56db;color:#1a56db}
.design-tab.active{border-color:#1a56db;background:#eff6ff;color:#1a56db}
.design-dot{width:12px;height:12px;border-radius:50%;flex-shrink:0}
.main-card{background:white;border-radius:14px;box-shadow:0 1px 3px rgba(0,0,0,.08),0 0 0 1px rgba(0,0,0,.06);overflow:hidden}
.card-body{display:grid;grid-template-columns:1fr 1fr}
@media(max-width:640px){.card-body{grid-template-columns:1fr}}
.form-section{padding:26px;border-right:1px solid rgba(0,0,0,.07)}
@media(max-width:640px){.form-section{border-right:none;border-bottom:1px solid rgba(0,0,0,.07)}}
.preview-section{padding:26px;display:flex;flex-direction:column;align-items:center;background:#f8fafc}
h2{font-size:15px;font-weight:700;margin-bottom:16px}
.upload-zone{border:2px dashed rgba(0,0,0,.18);border-radius:10px;padding:18px 14px;text-align:center;cursor:pointer;transition:all .15s;background:#f9fafb;position:relative;margin-bottom:14px}
.upload-zone:hover,.upload-zone.drag-over{border-color:#1a56db;background:#eff6ff}
.upload-zone input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
#photo-preview{width:68px;height:68px;border-radius:50%;object-fit:cover;border:3px solid #d4af37;display:none;margin:0 auto 7px}
.upload-icon{font-size:24px;margin-bottom:5px}
.upload-text{font-size:13px;color:#4b5563}
.upload-text strong{color:#1a56db}
.upload-hint{font-size:11px;color:#9ca3af;margin-top:3px}
.courtesy-section{background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:14px;margin-bottom:14px}
.courtesy-section h3{font-size:12px;font-weight:700;color:#92400e;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:10px}
.field label{display:block;font-size:13px;font-weight:600;margin-bottom:4px}
.field input[type=text]{width:100%;padding:9px 12px;border:1px solid rgba(0,0,0,.14);border-radius:8px;font-size:14px;font-family:inherit;outline:none;transition:border-color .15s}
.field input[type=text]:focus{border-color:#1a56db;box-shadow:0 0 0 3px rgba(26,86,219,.1)}
.btn-generate{width:100%;padding:12px;background:linear-gradient(135deg,#1a3a6b,#1a56db);color:white;border:none;border-radius:10px;font-size:15px;font-weight:700;cursor:pointer;transition:all .15s;font-family:inherit}
.btn-generate:hover{transform:translateY(-1px);box-shadow:0 4px 14px rgba(26,86,219,.3)}
.btn-generate:disabled{opacity:.55;cursor:not-allowed;transform:none;box-shadow:none}
.preview-label{font-size:11px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px}
#preview-img{width:100%;max-width:320px;border-radius:10px;box-shadow:0 4px 20px rgba(0,0,0,.14);display:none}
.preview-placeholder{width:100%;max-width:320px;background:linear-gradient(135deg,#dbeafe,#e0f2fe);border-radius:10px;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#93c5fd;font-size:13px;text-align:center;padding:28px 20px;gap:10px;aspect-ratio:1402/1122}
.preview-placeholder .big{font-size:36px}
.btn-download{margin-top:12px;padding:10px 24px;background:linear-gradient(135deg,#15803d,#16a34a);color:white;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;font-family:inherit;display:none;transition:all .15s}
.btn-download:hover{transform:translateY(-1px);box-shadow:0 3px 10px rgba(21,128,61,.3)}
.loading{display:none;align-items:center;gap:10px;font-size:13px;color:#6b7280;margin-top:10px}
.spinner{width:18px;height:18px;border:2px solid rgba(26,86,219,.2);border-top-color:#1a56db;border-radius:50%;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.error-msg{background:#fef2f2;border:1px solid #fecaca;color:#b91c1c;padding:10px 13px;border-radius:8px;font-size:13px;margin-top:10px;display:none}
footer{text-align:center;margin-top:26px;font-size:12px;color:#9ca3af}
</style>
</head>
<body>
<div class="container">
  <div class="hero">
    <div class="hero-badge">🇳🇬 Bamidele Salam Campaign</div>
    <h1>BSE4 Initiative — Create Your Support Frame</h1>
    <p>Upload your photo, enter your name, pick a colour — download instantly.</p>
  </div>

  <div class="design-tabs">
    <button class="design-tab active" data-id="1" onclick="selectDesign(1)"><span class="design-dot" style="background:linear-gradient(135deg,#1a6b2a,#1a3a6b)"></span>Classic Green</button>
    <button class="design-tab" data-id="2" onclick="selectDesign(2)"><span class="design-dot" style="background:linear-gradient(135deg,#1a3a8b,#0a1f5c)"></span>Royal Blue</button>
    <button class="design-tab" data-id="3" onclick="selectDesign(3)"><span class="design-dot" style="background:linear-gradient(135deg,#8b6914,#2c1f00)"></span>Gold & Black</button>
    <button class="design-tab" data-id="4" onclick="selectDesign(4)"><span class="design-dot" style="background:linear-gradient(135deg,#0a6b2a,#004d1a)"></span>Emerald Pride</button>
    <button class="design-tab" data-id="5" onclick="selectDesign(5)"><span class="design-dot" style="background:linear-gradient(135deg,#8b1a1a,#4d0000)"></span>Crimson Power</button>
  </div>

  <div class="main-card">
    <div class="card-body">
      <div class="form-section">
        <h2>📋 Your Details</h2>
        <div class="upload-zone" id="upload-zone">
          <input type="file" id="photo-input" accept="image/*" onchange="handlePhoto(this)">
          <img id="photo-preview" src="" alt="">
          <div id="upload-ui">
            <div class="upload-icon">📷</div>
            <div class="upload-text"><strong>Click to upload</strong> or drag & drop</div>
            <div class="upload-hint">JPG, PNG, WEBP · Clear background works best</div>
          </div>
        </div>

        <div class="courtesy-section">
          <h3>✍️ Courtesy</h3>
          <div class="field">
            <label>Your Name <span style="color:#ef4444">*</span></label>
            <input type="text" id="name-input" placeholder="e.g. Hon. John Adeyemi" maxlength="45">
          </div>
        </div>

        <button class="btn-generate" id="gen-btn" onclick="generate()">✨ Generate My Frame</button>
        <div class="loading" id="loading"><div class="spinner"></div><span id="loading-msg">Generating your poster…</span></div>
        <div class="error-msg" id="error-msg"></div>
      </div>

      <div class="preview-section">
        <div class="preview-label">Preview</div>
        <div class="preview-placeholder" id="ph-placeholder">
          <div class="big">🖼️</div>
          <div>Your poster appears here after you click <strong>Generate</strong></div>
        </div>
        <img id="preview-img" src="" alt="Generated Frame">
        <button class="btn-download" id="dl-btn" onclick="downloadImage()">⬇️ Download Image</button>
      </div>
    </div>
  </div>
  <footer>BSE4 Initiative · 10,000 Declaration · Iranse Rere &nbsp;|&nbsp; Rep. Bamidele Salam · Continuity · Service · Results</footer>
</div>

<script>
let selectedDesign=1, generatedBlob=null, photoFile=null;
function selectDesign(id){
  selectedDesign=id;
  document.querySelectorAll('.design-tab').forEach(t=>t.classList.remove('active'));
  document.querySelector('[data-id="'+id+'"]').classList.add('active');
}
function handlePhoto(input){
  const file=input.files[0]; if(!file) return;
  photoFile=file;
  const r=new FileReader();
  r.onload=e=>{
    const p=document.getElementById('photo-preview');
    p.src=e.target.result; p.style.display='block';
    document.getElementById('upload-ui').style.display='none';
  };
  r.readAsDataURL(file);
}
const zone=document.getElementById('upload-zone');
zone.addEventListener('dragover',e=>{e.preventDefault();zone.classList.add('drag-over')});
zone.addEventListener('dragleave',()=>zone.classList.remove('drag-over'));
zone.addEventListener('drop',e=>{
  e.preventDefault();zone.classList.remove('drag-over');
  const f=e.dataTransfer.files[0];
  if(f&&f.type.startsWith('image/')) handlePhoto({files:e.dataTransfer.files});
});
async function generate(){
  const name=document.getElementById('name-input').value.trim();
  const err=document.getElementById('error-msg');
  err.style.display='none';
  if(!photoFile){showError('Please upload your photo first.');return;}
  if(!name){showError('Please enter your name in the Courtesy section.');return;}
  document.getElementById('gen-btn').disabled=true;
  document.getElementById('loading').style.display='flex';
  document.getElementById('preview-img').style.display='none';
  document.getElementById('ph-placeholder').style.display='flex';
  document.getElementById('dl-btn').style.display='none';
  const t=setTimeout(()=>{const el=document.getElementById('loading-msg');if(el)el.textContent='Almost done…';},3500);
  try{
    const fd=new FormData();
    fd.append('photo',photoFile);
    fd.append('name',name);
    fd.append('design',selectedDesign);
    const res=await fetch('/generate',{method:'POST',body:fd});
    if(!res.ok){const e=await res.json();throw new Error(e.error||'Server error');}
    const blob=await res.blob();
    generatedBlob=blob;
    const url=URL.createObjectURL(blob);
    document.getElementById('preview-img').src=url;
    document.getElementById('preview-img').style.display='block';
    document.getElementById('ph-placeholder').style.display='none';
    document.getElementById('dl-btn').style.display='inline-block';
  }catch(e){showError(e.message);}
  finally{
    clearTimeout(t);
    document.getElementById('gen-btn').disabled=false;
    document.getElementById('loading').style.display='none';
  }
}
function downloadImage(){
  if(!generatedBlob)return;
  const name=document.getElementById('name-input').value.trim().replace(/[^a-zA-Z0-9 ]/g,'').replace(/ +/g,'_')||'frame';
  const a=document.createElement('a');
  a.href=URL.createObjectURL(generatedBlob);
  a.download='BSE4_'+name+'.jpg';
  a.click();
}
function showError(msg){
  const el=document.getElementById('error-msg');
  el.textContent=msg;el.style.display='block';
}
</script>
</body>
</html>'''

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/generate', methods=['POST'])
def generate():
    try:
        photo     = request.files.get('photo')
        name      = request.form.get('name','').strip()
        design_id = int(request.form.get('design', 1))
        if not photo:
            return jsonify({'error':'Photo is required'}), 400
        if not name:
            return jsonify({'error':'Name is required'}), 400
        photo_bytes = photo.read()
        result = composite_t2(photo_bytes, name, design_id)
        return send_file(result, mimetype='image/jpeg')
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5050)), debug=False)
