from flask import Flask, render_template, request, send_file
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display
from io import BytesIO
from PIL import Image
import time
import warnings
import os

# Ignore specific warnings
warnings.filterwarnings("ignore", category=UserWarning)

app = Flask(__name__)

class PDF(FPDF):
    def __init__(self, header, chapter_title, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.header_text = header
        self.chapter_title_text = chapter_title

    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, self.header_text, 0, 1, 'C')

    def chapter_title(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, self.chapter_title_text, 0, 1, 'L')

    def chapter_body(self, body):
        self.set_font('Amiri', '', 12)
        reshaped_text = arabic_reshaper.reshape(body)
        bidi_text = get_display(reshaped_text)
        self.multi_cell(0, 10, bidi_text)
        self.ln()

    def add_arabic_text(self, text, images):
        self.add_page()
        self.chapter_title()
        
        parts = text.split("{{image}}")
        for i, part in enumerate(parts):
            self.chapter_body(part)
            if i < len(images):
                self.add_image(images[i])

    def add_image(self, image_path):
        self.image(image_path, x=10, y=None, w=100)
        self.ln(10)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        header = request.form['header']
        chapter_title = request.form['chapter_title']
        title = request.form['title']
        text = request.form['text']
        filename = request.form['filename']
        
        # List of images from user upload
        uploaded_files = request.files.getlist("images")
        image_paths = []
        
        for file in uploaded_files:
            if file and file.filename != '':
                image_path = os.path.join('static', file.filename)
                file.save(image_path)
                image_paths.append(image_path)
        
        # Initialize PDF
        pdf = PDF(header, chapter_title)
        font_path = os.path.join('static', 'Amiri-Regular.ttf')
        if not os.path.exists(font_path):
            return f"Font file not found at {font_path}. Please make sure 'Amiri-Regular.ttf' is in the 'static' folder."

        try:
            pdf.add_font('Amiri', '', font_path, uni=True)
        except Exception as e:
            return f"Failed to add font: {str(e)}"
        
        # Add the Arabic text with images
        try:
            pdf.add_arabic_text(text, image_paths)
        except Exception as e:
            return f"Failed to add Arabic text: {str(e)}"
        
        # Save the PDF to a file
        try:
            pdf_file = f"{filename}_{time.strftime('%d-%m-%Y_%H-%M-%S')}.pdf"
            pdf.output(pdf_file)
        except Exception as e:
            return f"Failed to save PDF: {str(e)}"
        
        try:
            return send_file(pdf_file, as_attachment=True)
        except Exception as e:
            return f"Failed to send PDF file: {str(e)}"
    
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
