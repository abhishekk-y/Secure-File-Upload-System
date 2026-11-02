"""Generate the final concise editable deck and matching PDF."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.oxml.xmlchemy import OxmlElement
import math
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs'
suite=ET.parse(DOCS/'test-results.xml').getroot().find('testsuite')
tests=int(suite.attrib['tests']); failures=int(suite.attrib['failures'])+int(suite.attrib['errors'])
bandit=json.loads((DOCS/'bandit-results.json').read_text())['metrics']['_totals']
audit=json.loads((DOCS/'dependency-audit.json').read_text())
vulnerabilities=sum(len(d.get('vulns',[])) for d in audit.get('dependencies',[]))
deck=Presentation();deck.slide_width=Inches(13.333333);deck.slide_height=Inches(7.5)
pdf=canvas.Canvas(str(DOCS/'PRESENTATION.pdf'),pagesize=(960,540))
INK='25232E';PAPER='F8F5ED';PURPLE='D8CCEF';MINT='DFEBDD';GRAY='625E6A';LINE='D6D0DC'
notes=[]
slide=None


def box(x,y,w,h,fill=PAPER,line=None,radius=False):
    shape=slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,Inches(x/72),Inches(y/72),Inches(w/72),Inches(h/72))
    shape.fill.solid();shape.fill.fore_color.rgb=RGBColor.from_string(fill)
    if line:shape.line.color.rgb=RGBColor.from_string(line)
    else:shape.line.fill.background()
    pdf.setFillColor(colors.HexColor('#'+fill));pdf.setStrokeColor(colors.HexColor('#'+(line or fill)))
    pdf.rect(x,540-y-h,w,h,fill=1,stroke=bool(line))


def text(x,y,w,h,value,size=18,bold=False,color=INK):
    value=str(value)
    paragraph=Paragraph(escape(value).replace('\n','<br/>'),ParagraphStyle('s',fontName='Helvetica-Bold' if bold else 'Helvetica',fontSize=size,leading=size*1.25,textColor=colors.HexColor('#'+color)))
    _,height=paragraph.wrap(w,h)
    if height>h+1:raise ValueError(f'Slide text overflow: {value[:50]} {height} > {h}')
    paragraph.drawOn(pdf,x,540-y-height)
    shape=slide.shapes.add_textbox(Inches(x/72),Inches(y/72),Inches(w/72),Inches(h/72))
    frame=shape.text_frame;frame.word_wrap=True
    frame.margin_left=frame.margin_right=frame.margin_top=frame.margin_bottom=0
    for index,line in enumerate(value.split('\n')):
        p=frame.paragraphs[0] if index==0 else frame.add_paragraph()
        p.space_after=Pt(0);p.line_spacing=1.25
        r=p.add_run();r.text=line;r.font.name='Arial';r.font.size=Pt(size);r.font.bold=bold;r.font.color.rgb=RGBColor.from_string(color)


def logo(x,y,size=35):
    box(x,y,size,size,INK)
    box(x+size*.22,y+size*.18,size*.56,size*.64,PURPLE)
    box(x+size*.46,y+size*.35,size*.08,size*.29,INK)
    box(x+size*.35,y+size*.46,size*.30,size*.08,INK)


def start(number,title,subtitle,note):
    global slide
    slide=deck.slides.add_slide(deck.slide_layouts[6])
    box(0,0,960,540,PAPER)
    logo(38,25,26);text(76,30,720,20,'SECUREVAULT  /  SECURE FILE UPLOAD SYSTEM',10,True)
    text(38,77,884,57,title,31,True)
    text(38,139,884,42,subtitle,15,color=GRAY)
    text(38,515,820,18,'SecureVault  /  Cybersecurity project',9,color=GRAY)
    text(890,512,45,20,f'{number:02d}/12',10,True)
    slide.notes_slide.notes_text_frame.text=note
    notes.extend([f'## Slide {number} {title}',note,''])


def finish():pdf.showPage()


def table(x,y,widths,rows,row_h=49):
    for r,row in enumerate(rows):
        offset=x
        for c,value in enumerate(row):
            box(offset,y+r*row_h,widths[c],row_h,INK if r==0 else ('FFFFFF' if r%2 else 'EEE9F4'),LINE)
            text(offset+10,y+r*row_h+10,widths[c]-20,row_h-15,value,12 if r else 12, r==0, 'FFFFFF' if r==0 else INK)
            offset+=widths[c]


def card(x,y,w,h,title,body,fill=PURPLE):
    box(x+4,y+4,w,h,INK);box(x,y,w,h,fill,INK)
    text(x+15,y+15,w-30,45,title,18,True)
    text(x+15,y+66,w-30,h-76,body,14)


def arrow(x1,y1,x2,y2,color=GRAY):
    connector=slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,Inches(x1/72),Inches(y1/72),Inches(x2/72),Inches(y2/72))
    connector.line.color.rgb=RGBColor.from_string(color);connector.line.width=Pt(2)
    end=OxmlElement('a:tailEnd');end.set('type','triangle');connector.line._get_or_add_ln().append(end)
    pdf.setStrokeColor(colors.HexColor('#'+color));pdf.setFillColor(colors.HexColor('#'+color));pdf.setLineWidth(2)
    pdf.line(x1,540-y1,x2,540-y2)
    angle=math.atan2(y2-y1,x2-x1)
    path=pdf.beginPath();path.moveTo(x2,540-y2)
    for delta in (-.45,.45):
        path.lineTo(x2-9*math.cos(angle+delta),540-(y2-9*math.sin(angle+delta)))
    path.close();pdf.drawPath(path,fill=1,stroke=0)


def roundel(x,y,size,value,fill=PURPLE,color=INK):
    shape=slide.shapes.add_shape(MSO_SHAPE.OVAL,Inches(x/72),Inches(y/72),Inches(size/72),Inches(size/72))
    shape.fill.solid();shape.fill.fore_color.rgb=RGBColor.from_string(fill);shape.line.fill.background()
    pdf.setFillColor(colors.HexColor('#'+fill));pdf.circle(x+size/2,540-y-size/2,size/2,fill=1,stroke=0)
    text(x+size*.28,y+size*.24,size*.6,size*.6,value,size*.37,True,color)


def label(x,y,w,title,body,fill='FFFFFF'):
    box(x,y,w,102,fill,LINE)
    text(x+16,y+14,w-32,29,title,18,True)
    text(x+16,y+51,w-32,43,body,14,color=GRAY)


def picture(path,x,y,w,h):
    with Image.open(path) as im:
        scale=min(w/im.width,h/im.height);iw=im.width*scale;ih=im.height*scale
    slide.shapes.add_picture(str(path),Inches(x/72),Inches(y/72),width=Inches(iw/72),height=Inches(ih/72))
    pdf.drawImage(str(path),x,540-y-ih,iw,ih)


start(1,'SecureVault','', 'Introduce SecureVault as an academic Secure File Upload System. Replace the student/institution fields on this slide. The presentation distinguishes verified local controls from enterprise services requiring licenses.')
box(0,0,960,540,INK)
logo(46,38,40)
text(104,45,700,28,'SECURE FILE UPLOAD SYSTEM',13,True,'D8CCEF')
text(46,127,690,80,'SecureVault',57,True,'FFFFFF')
text(49,221,650,101,'Private files.\nVisible security controls.',34,False,'F8F5ED')
text(50,354,540,68,'An inspectable workflow for validation, reconstruction, encrypted storage and deliberate sharing.',19,color='D8CCEF')
box(749,148,134,166,PURPLE)
box(767,169,98,124,INK)
roundel(786,209,60,'+',PURPLE)
text(50,479,750,26,'[Student name]  /  [Enrollment number]  /  [Institution]',13,color='D8CCEF')
text(881,491,40,20,'01/12',10,True,'FFFFFF')
finish()

start(2,'An upload is a trust decision.','The project makes that decision visible and testable.','Describe the three risks, then show the actual earlier workspace screenshot. The final source additionally supports document formats and inspection reports; the screenshot is not an exhaustive feature list.')
for y,n,title,body in [(196,'1','Deceptive files','Names and MIME declarations can lie.'),(292,'2','Unnecessary exposure','Metadata and public links can reveal information.'),(388,'3','Missing evidence','Users need to know which checks actually ran.')]:
    roundel(40,y,37,n)
    text(93,y,335,31,title,20,True)
    text(93,y+36,335,49,body,16,color=GRAY)
box(465,195,455,289,'FFFFFF',LINE)
picture(DOCS/'screenshots/vault.png',477,210,431,238)
text(481,455,415,21,'Actual workspace capture with synthetic demo files',10,color=GRAY)
finish()

start(3,'Research to implementation','Three selected papers, translated into specific engineering choices.','The corpus is purposive: one paper each in 2020, 2022 and 2024. No citation-count or global trend claim is made. Full records and URLs are in the report and literature-corpus.csv.')
table(38,200,[235,320,329],[['Research','What it contributes','Our implementation'],['Eian et al. / 2020','Practical secure-development guidance','Security requirements become acceptance tests'],['Kudriavtseva & Gadyatskaya / 2022','Review of 28 secure SDLC methodologies','Design, operational responsibilities and evidence'],['Neef & Oudeh / 2024 / FUEL','Varied file-upload scanner evaluation','Negative cases; no reliance on antivirus alone']],66)
text(41,479,870,22,'Design guidance: OWASP File Upload Cheat Sheet + NIST SP 800-218 SSDF',13,True)
finish()

start(4,'System architecture','Separate responsibilities. Explicit trust boundaries.','Browser bytes are untrusted. The server holds encryption keys. Reconstruction runs in separate bounded processes; this is not a hardened malware sandbox or dynamic execution environment.')
label(38,202,184,'Browser','Forms, progress\nand inspection',PURPLE)
label(280,202,260,'Flask + Waitress','Identity, CSRF, validation\nand sharing policy',MINT)
label(602,202,320,'Processing services','Reconstruction worker, OpenCV\nand local ClamAV',PURPLE)
arrow(224,252,277,252);arrow(543,252,598,252)
arrow(410,307,410,361);arrow(760,307,760,361)
label(280,368,260,'SQLite','Ownership, sessions,\nreports, codes and audit')
label(602,368,320,'Private encrypted vault','Fernet blobs; separate signing,\nencryption and audit keys')
text(42,366,190,101,'No upload directory\nis publicly served.\n\nNo cloud scanner receives files.',15,color=GRAY)
finish()

start(5,'From upload to one-use delivery','The technical workflow—and where rejection happens.','Explain each gate in order. ClamAV scans the original and changed output. DLP can allow private storage but deny sharing. The code is consumed atomically before network delivery completes.')
for x,n,title,body in [(38,'01','Authenticate','Session + CSRF'),(343,'02','Inspect','Type, size, hash + AV'),(648,'03','Reconstruct','Parser + normalization')]:
    roundel(x,199,34,n)
    text(x+47,200,225,30,title,20,True)
    box(x,243,270,65,'FFFFFF',LINE);text(x+14,260,245,35,body,15)
arrow(309,277,339,277);arrow(614,277,644,277);arrow(783,312,783,346)
for x,n,title,body in [(648,'04','Analyze','DLP + output antivirus'),(343,'05','Encrypt','Quota + private storage'),(38,'06','Share','Policy + one-use code')]:
    roundel(x,350,34,n)
    text(x+47,351,225,30,title,20,True)
    box(x,394,270,65,'FFFFFF',LINE);text(x+14,411,245,35,body,15)
arrow(644,426,614,426);arrow(339,426,309,426)
text(40,480,880,23,'Failure -> reject and record the reason. Sensitive-data findings -> private access only.',13,True)
finish()

start(6,'Technology you can locate in the code','A compact stack with clear ownership of each concern.','Use the file tree to answer where a feature is implemented. The full report contains the complete schema, SRS and algorithms. All security decisions are enforced server-side.')
box(38,195,407,297,INK)
text(57,215,366,34,'PROJECT MAP',13,True,'D8CCEF')
text(57,260,365,221,'app/\n  __init__.py\n  security_engines.py\n  content_worker.py\n  document_scanner.py\n  templates/ + static/\ntests/   scripts/   docs/',18,color='FFFFFF')
for y,title,body in [(198,'Flask + SQLite + Waitress','Routes, transactions and sessions'),(271,'Pillow + OpenCV + PDFium','Image handling and reconstruction'),(344,'Fernet + scrypt + PyOTP','Encryption, passwords and MFA'),(417,'pytest + Bandit + pip-audit','Regression and dependency evidence')]:
    text(480,y,439,30,title,20,True)
    text(480,y+34,439,30,body,15,color=GRAY)
finish()

start(7,'Advanced features, honest outcomes','The interface separates document processing from malware checks.','Reconstruction is deliberately lossy. OpenCV cleans page images. YARA-X gives local rule matches; Tesseract OCR adds text for DLP. Neither guarantees detection.')
card(38,198,276,257,'Reconstruct','PDF -> image-only pages\nDOCX -> plain paragraphs\nCSV -> formula protection\nHTML/XML/SVG -> restricted content',PURPLE)
card(342,198,276,257,'Inspect','ClamAV antivirus\nYARA-X local rules\nTesseract OCR assisted DLP\nPer-file report + SHA-256',MINT)
card(646,198,276,257,'Control','OpenCV page enhancement\nPrivate encrypted storage\nDLP restriction on sharing\n15-minute, single-use code',PURPLE)
text(41,478,874,24,'Supported: TXT · PNG · JPEG · PDF · DOCX · CSV · HTML · XML · restricted SVG',13,True)
finish()

start(8,'Access is a relationship, not a filename.','The data model makes ownership and sharing explicit.','Each file belongs to an owner. Sessions contain hashed tokens. Shares contain hashed capabilities, expiry and use state. HMAC audit chains detect edits/interior deletion but not suffix truncation without an external checkpoint.')
label(38,205,190,'User','Password hash\nEncrypted TOTP',PURPLE)
label(296,205,250,'Files','Owner + MIME + size\nFingerprint + inspection',MINT)
label(614,205,308,'Share codes','File + owner + token hash\nExpiry + atomic used state',PURPLE)
arrow(231,255,292,255);arrow(549,255,610,255)
label(38,365,190,'Sessions','Token hash\nAbsolute expiry')
label(296,365,250,'Audit events','Owner + event fields\nHMAC-linked history')
label(614,365,308,'Blocked hashes','Operator SHA-256 denylist\nChecked on new uploads')
arrow(130,311,130,361);arrow(224,298,296,368)
text(40,482,880,21,'Owner checks on every private route. File integrity is rechecked before delivery and reports.',12,True)
finish()

start(9,'Why this design is distinctive','The contribution is integrated, explainable security—not new cryptography.','Compare alternatives without claiming a benchmark. The design favors local inspectability. High throughput, key management and hardened isolation require additional infrastructure.')
table(38,196,[255,340,289],[['Decision','Why it helps','Accepted tradeoff'],['Reconstruct instead of retain','Reduce original active document structure','Some fidelity is lost'],['One-use codes + DLP gate','Deliberate sharing with visible restrictions','Code delivery must be trusted'],['Per-file inspection evidence','Explain what ran and verify integrity now','Not an independent certificate']],64)
text(42,465,870,40,'Explainable controls, visible outcomes and clear limits.',22,True)
finish()

start(10,'SDLC and future scope','Security requirements remain visible through delivery.','There is no invented six-week schedule. Current functionality and future service integrations are explicitly separated. Public operation requires HTTPS, protected backups and deployment verification.')
phases=['Define','Design','Build','Verify','Operate']
for i,phase in enumerate(phases):
    x=38+i*180;roundel(x,200,37,str(i+1));text(x+46,207,130,30,phase,17,True)
    if i<4:arrow(x+151,219,x+174,219)
card(38,285,414,196,'Delivered','SRS + threat model + alternatives\nWorking local security controls\nRegression and inspection evidence\nReport, synopsis and 12-slide deck',MINT)
card(487,285,435,196,'Next','Licensed multi-engine / CDR integration\nHardened isolated sandbox service\nPasskeys and managed key rotation\nExternal audit checkpoints and scaling',PURPLE)
finish()

start(11,'Demonstrate. Explain. Defend.','Use synthetic samples and show the security report.','Full references: OWASP File Upload Cheat Sheet; NIST SP800-218; arxiv.org/abs/2012.05540; arxiv.org/abs/2211.16987; arxiv.org/abs/2405.16619; docs.opencv.org; pypdfium2.readthedocs.io; docs.clamav.net. Replace student fields before presenting.')
text(41,205,408,41,'A five-step demonstration',22,True)
text(42,260,400,227,'01  Upload a supported sample.\n02  Scan the document photo.\n03  Inspect processing and AV results.\n04  Share once; show reuse denial.\n05  Explain DLP and integrity checks.',18)
box(481,197,440,292,'FFFFFF',LINE)
text(503,213,399,31,'Primary references',20,True)
text(503,264,394,218,'OWASP / File Upload Cheat Sheet\nNIST / SP 800-218 Secure SDLC\nEian (2020) / secure development\nKudriavtseva (2022) / methodology review\nNeef (2024) / FUEL scanner evaluation\nOpenCV, PDFium and ClamAV documentation\n\nFull URLs: PROJECT_REPORT.md and RESEARCH.md',13,color=GRAY)
finish()

start(12,'A visual tour of SecureVault','Workspace and upload screens from the project interface.','Use these interface captures to orient the audience before the live workflow. Demonstrate current YARA-X and OCR status in the owner inspection report because the reported state depends on local scanner configuration.')
for x,filename,caption in [(40,'vault.png','01  Private file workspace'),(495,'upload.png','02  Upload and OpenCV option')]:
    box(x,194,424,282,'FFFFFF',LINE)
    picture(DOCS/'screenshots'/filename,x+9,203,406,240)
    text(x+12,451,400,18,caption,12,True)
text(42,494,870,20,'Interface captures are earlier project screenshots; show current scanner outcomes in the live inspection report.',11,color=GRAY)
finish()

deck.save(DOCS/'PRESENTATION.pptx');pdf.save()
(DOCS/'PRESENTATION_NOTES.md').write_text('# Presentation speaker notes\n\n'+'\n'.join(notes),encoding='utf-8')
print('Created redesigned 12-slide presentation and speaker notes')
