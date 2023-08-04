from flask import Flask, render_template, send_file
from fpdf import FPDF
from io import BytesIO

import json

app = Flask(__name__)


def load_products_info_from_json():
    with open('static/sorted_products_info.json') as json_file:
        return json.load(json_file)


def create_pdf(products_info, max_calories):
    pdf = FPDF()
    pdf.add_page()

    # Set font style and size
    pdf.set_font("Arial", size=12)

    # Add content to the PDF
    for product_info in products_info:
        # Write the product link and calories to the PDF
        pdf.cell(0, 10, f"Name: {product_info.name}", ln=True)
        pdf.cell(0, 10, f"Price: {product_info.price}", ln=True)
        pdf.cell(0, 10, f"Image: {product_info.imageSrc}", ln=True)
        pdf.cell(0, 10, f"link: {product_info.link}", ln=True)
        pdf.cell(0, 10, f"Summary: {product_info.summary}", ln=True)
        pdf.cell(0, 10, f"Description: {product_info.description}", ln=True)
        pdf.cell(0, 10, f"Measured content: {product_info.measuredContent}", ln=True)
        pdf.cell(0, 10, f"Calories: {product_info.calories}", ln=True)
        pdf.cell(0, 10, f"Protein: {product_info.protein}", ln=True)
        pdf.cell(0, 10, "", ln=True)  # Add empty line between entries

    # Save the PDF to a BytesIO buffer
    pdf_buffer = BytesIO()
    pdf.output(pdf_buffer)
    pdf_buffer.seek(0)

    # Return the BytesIO buffer with the appropriate content type for download
    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"products_info_within_calorie_range_of_{max_calories}.pdf"
    )


# Route to trigger PDF creation and download
@app.route('/generate_pdf')
def generate_pdf():
    # Assuming you already have the sorted_products_info and max_calories (replace with actual data)
    sorted_products_info = load_products_info_from_json()
    max_calories = 300

    # Call the create_pdf function to generate the PDF
    return create_pdf(sorted_products_info, max_calories)


# Route to display the sorted product info in a beautiful way
@app.route('/')
def display_sorted_products_info():
    sorted_products_info = load_products_info_from_json()

    # Pass the data to the template for rendering
    return render_template('index.html', sorted_products_info=sorted_products_info)


if __name__ == '__main__':
    app.run(debug=True)
