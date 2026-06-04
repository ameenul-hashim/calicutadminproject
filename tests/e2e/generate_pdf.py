from reportlab.pdfgen import canvas
import os

def create_pdf(filename):
    c = canvas.Canvas(filename)
    c.drawString(100, 750, "NeoLearn LMS Test Document")
    c.drawString(100, 730, "This is a valid PDF for E2E testing.")
    c.save()

if __name__ == "__main__":
    create_pdf("test_resource.pdf")
    print("Created test_resource.pdf")
