from flask import Flask, request, jsonify, send_file, render_template_string
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from rembg import remove as rembg_remove
import io, os, traceback

app = Flask(__name__)
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), 'template.png')

# Template: 1092 x 1440
# Photo box (inside gold border): x1=218, y1=140, x2=938, y2=695
# Courtesy white box: y=1156–1440, x=190–900
# "Courtesy:" red script already printed at y≈1306–1346
# Name goes at y=1358, title at y=1410

PHOTO_X1, PHOTO_Y1 = 218, 140
PHOTO_X2, PHOTO_Y2 = 938, 695
PHOTO_W = PHOTO_X2 - PHOTO_X1   # 720
PHOTO_H = PHOTO_Y2 - PHOTO_Y1   # 555

COURTESY_X1, COURTESY_X2 = 190, 900
COURTESY_CX = (COURTESY_X1 + COURTESY_X2) // 2  # 545
NAME_Y   = 1358
TITLE_Y  = 1410

DESIGNS = [
    {"id":1,"label":"Classic Green","swatch":"linear-gradient(135deg,#1a6b2a,#1a3a6b)","overlay":None,         "name_color":(10,10,10),  "title_color":(50,50,50)},
    {"id":2,"label":"Royal Blue",   "swatch":"linear-gradient(135deg,#1a3a8b,#0a1f5c)","overlay":(0,20,80,50), "name_color":(5,10,70),   "title_color":(20,30,110)},
    {"id":3,"label":"Gold & Black", "swatch":"linear-gradient(135deg,#8b6914,#2c1f00)","overlay":(50,25,0,40), "name_color":(70,40,0),   "title_color":(100,65,0)},
    {"id":4,"label":"Emerald Pride","swatch":"linear-gradient(135deg,#0a6b2a,#004d1a)","overlay":(0,55,20,40), "name_color":(0,65,25),   "title_color":(0,85,35)},
    {"id":5,"label":"Crimson Power","swatch":"linear-gradient(135deg,#8b1a1a,#4d0000)","overlay":(90,0,0,40),  "name_color":(100,0,0),   "title_color":(140,15,15)},
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

def composite_image(user_photo_bytes, courtesy_name, title_text, design_id):
    design = next(d for d in DESIGNS if d["id"] == design_id)

    template = Image.open(TEMPLATE_PATH).convert("RGBA")

    # Colour tint overlay
    if design["overlay"]:
        r, g, b, a = design["overlay"]
        template = Image.alpha_composite(template, Image.new("RGBA", template.size, (r, g, b, a)))

    # ── Remove background then paste into the gold-bordered rectangle ──
    # rembg strips the background; result is RGBA with transparent bg
    user_photo_bytes = rembg_remove(user_photo_bytes)
    user_img = Image.open(io.BytesIO(user_photo_bytes)).convert("RGBA")
    uw, uh = user_img.size

    # Contain-fit: scale down to fit entirely inside the box, no cropping
    # Letterbox with the template's own background showing through
    target_ratio = PHOTO_W / PHOTO_H
    src_ratio    = uw / uh
    if src_ratio > target_ratio:
        # wider than box — constrain by width
        fit_w = PHOTO_W
        fit_h = int(PHOTO_W / src_ratio)
    else:
        # taller than box — constrain by height
        fit_h = PHOTO_H
        fit_w = int(PHOTO_H * src_ratio)

    user_img = user_img.resize((fit_w, fit_h), Image.LANCZOS)

    # Crop the matching region from the template as the letterbox background
    # so transparent gaps show the template's own cream/green bg — not black
    template_bg = template.crop((PHOTO_X1, PHOTO_Y1, PHOTO_X2, PHOTO_Y2))

    # Centre the fitted image over the template background crop
    canvas = template_bg.copy().convert("RGBA")
    offset_x = (PHOTO_W - fit_w) // 2
    offset_y = (PHOTO_H - fit_h) // 2
    canvas.paste(user_img, (offset_x, offset_y), user_img)
    user_img = canvas

    # Rounded-rect mask (radius ~40px) matching the gold border
    mask = Image.new("L", (PHOTO_W, PHOTO_H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, PHOTO_W, PHOTO_H), radius=42, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=1))
    user_img.putalpha(mask)

    template.paste(user_img, (PHOTO_X1, PHOTO_Y1), user_img)

    # ── Write courtesy name & title ──
    draw = ImageDraw.Draw(template)
    box_width = COURTESY_X2 - COURTESY_X1 - 40

    # Auto-size name to fit
    name_font, name_sz = None, 20
    for sz in [46, 40, 34, 28, 24, 20]:
        f = get_font(sz, bold=True)
        nb = draw.textbbox((0, 0), courtesy_name, font=f)
        if (nb[2] - nb[0]) <= box_width:
            name_font, name_sz = f, sz
            break
    if not name_font:
        name_font, name_sz = get_font(20, bold=True), 20

    nb   = draw.textbbox((0, 0), courtesy_name, font=name_font)
    nx   = COURTESY_CX - (nb[2] - nb[0]) // 2
    # Shadow
    draw.text((nx + 1, NAME_Y + 1), courtesy_name, font=name_font, fill=(200, 200, 200, 150))
    draw.text((nx, NAME_Y), courtesy_name, font=name_font, fill=design["name_color"])

    # Title below name
    if title_text:
        tf = get_font(28, bold=False)
        tb = draw.textbbox((0, 0), title_text, font=tf)
        tx = COURTESY_CX - (tb[2] - tb[0]) // 2
        ty = NAME_Y + name_sz + 10
        draw.text((tx, ty), title_text, font=tf, fill=design["title_color"])

    buf = io.BytesIO()
    template.convert("RGB").save(buf, format="JPEG", quality=93)
    buf.seek(0)
    return buf


HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Rep. Bamidele Salam — Support Frame Generator</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',sans-serif;background:#f0f2f5;color:#111827;min-height:100vh;padding:24px 16px 48px}
.container{max-width:920px;margin:0 auto}
.hero{text-align:center;margin-bottom:26px}
.hero-badge{display:inline-flex;align-items:center;gap:6px;background:linear-gradient(135deg,#1a3a6b,#0f2444);color:#d4af37;font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;padding:6px 16px;border-radius:100px;margin-bottom:12px}
.hero h1{font-size:clamp(20px,5vw,30px);font-weight:800;color:#0f172a;margin-bottom:6px}
.hero p{font-size:14px;color:#4b5563;max-width:460px;margin:0 auto}
.design-tabs{display:flex;gap:8px;flex-wrap:wrap;justify-content:center;margin-bottom:22px}
.design-tab{display:flex;align-items:center;gap:8px;padding:8px 16px;border-radius:100px;border:2px solid rgba(0,0,0,0.1);background:white;cursor:pointer;font-size:13px;font-weight:600;color:#374151;transition:all .15s;font-family:inherit}
.design-tab:hover{border-color:#1a56db;color:#1a56db}
.design-tab.active{border-color:#1a56db;background:#eff6ff;color:#1a56db}
.design-dot{width:14px;height:14px;border-radius:50%;flex-shrink:0}
.main-card{background:white;border-radius:14px;box-shadow:0 1px 3px rgba(0,0,0,.08),0 0 0 1px rgba(0,0,0,.06);overflow:hidden}
.card-body{display:grid;grid-template-columns:1fr 1fr}
@media(max-width:620px){.card-body{grid-template-columns:1fr}}
.form-section{padding:28px;border-right:1px solid rgba(0,0,0,.07)}
@media(max-width:620px){.form-section{border-right:none;border-bottom:1px solid rgba(0,0,0,.07)}}
.preview-section{padding:28px;display:flex;flex-direction:column;align-items:center;background:#f8fafc}
h2{font-size:15px;font-weight:700;margin-bottom:20px}
.field{margin-bottom:16px}
label{display:block;font-size:13px;font-weight:600;margin-bottom:5px}
.req{color:#ef4444}.opt{color:#9ca3af;font-weight:400;font-size:12px}
input[type=text]{width:100%;padding:10px 13px;border:1px solid rgba(0,0,0,.14);border-radius:8px;font-size:14px;font-family:inherit;outline:none;transition:border-color .15s;background:white}
input[type=text]:focus{border-color:#1a56db;box-shadow:0 0 0 3px rgba(26,86,219,.1)}
.upload-zone{border:2px dashed rgba(0,0,0,.18);border-radius:10px;padding:20px 14px;text-align:center;cursor:pointer;transition:all .15s;background:#f9fafb;position:relative}
.upload-zone:hover,.upload-zone.drag-over{border-color:#1a56db;background:#eff6ff}
.upload-zone input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
#photo-preview{width:72px;height:72px;border-radius:50%;object-fit:cover;border:3px solid #d4af37;display:none;margin:0 auto 8px}
.upload-icon{font-size:26px;margin-bottom:6px}
.upload-text{font-size:13px;color:#4b5563}
.upload-text strong{color:#1a56db}
.upload-hint{font-size:11px;color:#9ca3af;margin-top:3px}
.btn-generate{width:100%;padding:13px;background:linear-gradient(135deg,#1a3a6b,#1a56db);color:white;border:none;border-radius:10px;font-size:15px;font-weight:700;cursor:pointer;transition:all .15s;margin-top:6px;font-family:inherit}
.btn-generate:hover{transform:translateY(-1px);box-shadow:0 4px 14px rgba(26,86,219,.3)}
.btn-generate:disabled{opacity:.55;cursor:not-allowed;transform:none;box-shadow:none}
.preview-label{font-size:11px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:1px;margin-bottom:14px}
#preview-img{width:100%;max-width:290px;border-radius:10px;box-shadow:0 4px 20px rgba(0,0,0,.14);display:none}
.preview-placeholder{width:100%;max-width:290px;aspect-ratio:1092/1440;background:linear-gradient(135deg,#dbeafe,#e0f2fe);border-radius:10px;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#93c5fd;font-size:13px;text-align:center;padding:20px;gap:10px}
.preview-placeholder .big{font-size:38px}
.btn-download{margin-top:14px;padding:10px 24px;background:linear-gradient(135deg,#15803d,#16a34a);color:white;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;font-family:inherit;display:none;transition:all .15s}
.btn-download:hover{transform:translateY(-1px);box-shadow:0 3px 10px rgba(21,128,61,.3)}
.loading{display:none;align-items:center;gap:10px;font-size:13px;color:#6b7280;margin-top:10px}
.spinner{width:18px;height:18px;border:2px solid rgba(26,86,219,.2);border-top-color:#1a56db;border-radius:50%;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.error-msg{background:#fef2f2;border:1px solid #fecaca;color:#b91c1c;padding:10px 13px;border-radius:8px;font-size:13px;margin-top:10px;display:none}
footer{text-align:center;margin-top:28px;font-size:12px;color:#9ca3af}
</style>
</head>
<body>
<div class="container">
  <div class="hero">
    <div class="hero-badge">🇳🇬 Bamidele Salam Campaign</div>
    <h1>Create Your Support Frame</h1>
    <p>Pick a design, upload your photo, enter your name — download your personalised poster instantly.</p>
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
        <div class="field">
          <label>Your Photo <span class="req">*</span></label>
          <div class="upload-zone" id="upload-zone">
            <input type="file" id="photo-input" accept="image/*" onchange="handlePhoto(this)">
            <img id="photo-preview" src="" alt="">
            <div id="upload-ui">
              <div class="upload-icon">📷</div>
              <div class="upload-text"><strong>Click to upload</strong> or drag & drop</div>
              <div class="upload-hint">JPG, PNG, WEBP · max 10MB</div>
            </div>
          </div>
        </div>
        <div class="field">
          <label>Your Name <span class="req">*</span></label>
          <input type="text" id="name-input" placeholder="e.g. Hon. John Adeyemi" maxlength="60">
        </div>
        <div class="field">
          <label>Title / Position <span class="opt">(optional)</span></label>
          <input type="text" id="title-input" placeholder="e.g. CEO Acme Corp" maxlength="60">
        </div>
        <button class="btn-generate" id="gen-btn" onclick="generate()">✨ Generate My Frame</button>
        <div class="loading" id="loading"><div class="spinner"></div><span id="loading-msg">Removing background…</span></div>
        <div class="error-msg" id="error-msg"></div>
      </div>
      <div class="preview-section">
        <div class="preview-label">Preview</div>
        <div class="preview-placeholder" id="preview-placeholder">
          <div class="big">🖼️</div>
          <div>Your poster appears here after you click <strong>Generate</strong></div>
        </div>
        <img id="preview-img" src="" alt="Generated Frame">
        <button class="btn-download" id="dl-btn" onclick="downloadImage()">⬇️ Download Image</button>
      </div>
    </div>
  </div>
  <footer>Rep. Bamidele Salam · 3rd Term · Continuity · Service · Results</footer>
</div>
<script>
let selectedDesign=1,generatedBlob=null,photoFile=null;
function selectDesign(id){selectedDesign=id;document.querySelectorAll('.design-tab').forEach(t=>t.classList.remove('active'));document.querySelector(`[data-id="${id}"]`).classList.add('active')}
function handlePhoto(input){const file=input.files[0];if(!file)return;photoFile=file;const r=new FileReader();r.onload=e=>{const p=document.getElementById('photo-preview');p.src=e.target.result;p.style.display='block';document.getElementById('upload-ui').style.display='none'};r.readAsDataURL(file)}
const zone=document.getElementById('upload-zone');
zone.addEventListener('dragover',e=>{e.preventDefault();zone.classList.add('drag-over')});
zone.addEventListener('dragleave',()=>zone.classList.remove('drag-over'));
zone.addEventListener('drop',e=>{e.preventDefault();zone.classList.remove('drag-over');const f=e.dataTransfer.files[0];if(f&&f.type.startsWith('image/')){document.getElementById('photo-input').files=e.dataTransfer.files;handlePhoto({files:e.dataTransfer.files})}});
async function generate(){
  const name=document.getElementById('name-input').value.trim();
  const title=document.getElementById('title-input').value.trim();
  const err=document.getElementById('error-msg');err.style.display='none';
  if(!photoFile){showError('Please upload your photo first.');return}
  if(!name){showError('Please enter your name.');return}
  document.getElementById('gen-btn').disabled=true;
  document.getElementById('loading').style.display='flex';
  document.getElementById('loading-msg').textContent='Removing background…';
  document.getElementById('preview-img').style.display='none';
  document.getElementById('preview-placeholder').style.display='flex';
  document.getElementById('dl-btn').style.display='none';
  // Update message after 3s to reassure user it's still working
  const msgTimer = setTimeout(()=>{
    const el=document.getElementById('loading-msg');
    if(el) el.textContent='Compositing your poster…';
  }, 3500);
  try{
    const fd=new FormData();fd.append('photo',photoFile);fd.append('name',name);fd.append('title',title);fd.append('design',selectedDesign);
    const res=await fetch('/generate',{method:'POST',body:fd});
    if(!res.ok){const e=await res.json();throw new Error(e.error||'Server error')}
    const blob=await res.blob();generatedBlob=blob;
    const url=URL.createObjectURL(blob);
    document.getElementById('preview-img').src=url;
    document.getElementById('preview-img').style.display='block';
    document.getElementById('preview-placeholder').style.display='none';
    document.getElementById('dl-btn').style.display='inline-block';
  }catch(e){showError(e.message)}
  finally{clearTimeout(msgTimer);document.getElementById('gen-btn').disabled=false;document.getElementById('loading').style.display='none'}
}
function downloadImage(){if(!generatedBlob)return;const n=document.getElementById('name-input').value.trim().replace(/[^a-zA-Z0-9 ]/g,'').replace(/ +/g,'_')||'frame';const a=document.createElement('a');a.href=URL.createObjectURL(generatedBlob);a.download=`Bamidele_Salam_${n}.jpg`;a.click()}
function showError(msg){const el=document.getElementById('error-msg');el.textContent=msg;el.style.display='block'}
</script>
</body>
</html>'''

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/generate', methods=['POST'])
def generate():
    try:
        photo=request.files.get('photo')
        name=request.form.get('name','').strip()
        title=request.form.get('title','').strip()
        design_id=int(request.form.get('design',1))
        if not photo or not name:
            return jsonify({'error':'Photo and name are required'}),400
        result=composite_image(photo.read(),name,title,design_id)
        return send_file(result,mimetype='image/jpeg')
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error':str(e)}),500

if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5050)), debug=False)
