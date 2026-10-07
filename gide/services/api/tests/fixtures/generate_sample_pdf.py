import pymupdf
from pathlib import Path

def create_sample_pdf(output_path: str):
    doc = pymupdf.open()

    # Page 1: Chapter 1 Introduction
    page1 = doc.new_page(width=595, height=842)
    # Heading
    page1.insert_text((50, 70), "CHAPTER 1: INTRODUCTION TO MACHINE LEARNING", fontsize=16, fontname="helv", color=(0.1, 0.2, 0.5))
    # Paragraph 1
    p1 = (
        "Machine learning is a subfield of artificial intelligence focused on building systems that learn "
        "from data. Rather than explicitly programming every rule, machine learning algorithms iteratively "
        "adjust internal parameters to minimize loss on empirical observations."
    )
    page1.insert_textbox(pymupdf.Rect(50, 100, 545, 200), p1, fontsize=11, fontname="helv")
    
    # Paragraph 2
    p2 = (
        "A foundational taxonomy partitions machine learning into supervised learning, unsupervised learning, "
        "and reinforcement learning. In supervised learning, the model is provided with paired training instances "
        "(x, y), where x denotes the feature vector and y denotes the target ground truth label."
    )
    page1.insert_textbox(pymupdf.Rect(50, 210, 545, 310), p2, fontsize=11, fontname="helv")

    # Page 2: Mathematical Formulations
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((50, 70), "SECTION 1.2: SUPERVISED OPTIMIZATION OBJECTIVES", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.5))
    p3 = (
        "Consider empirical risk minimization (ERM). Given a hypothesis class H and a convex surrogate loss function "
        "L(f(x), y), the objective is to find parameters theta that minimize the regularized sample average loss:\n\n"
        "min_{theta} (1/N) * sum_{i=1}^N L(f_theta(x_i), y_i) + lambda * R(theta)\n\n"
        "Here, lambda represents the regularization hyperparameter controlling the trade-off between bias and variance."
    )
    page2.insert_textbox(pymupdf.Rect(50, 100, 545, 250), p3, fontsize=11, fontname="helv")

    # Page 3: Diagrams & Architecture
    page3 = doc.new_page(width=595, height=842)
    page3.insert_text((50, 70), "SECTION 1.3: ARCHITECTURAL FLOW AND GRADIENT DESCENT", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.5))
    p4 = (
        "Below is a schematic diagram illustrating the forward inference pass, error calculation, and "
        "backward automatic differentiation pass via stochastic gradient descent (SGD)."
    )
    page3.insert_textbox(pymupdf.Rect(50, 100, 545, 170), p4, fontsize=11, fontname="helv")

    # Draw a vector diagram with shapes
    shape = page3.new_shape()
    # Box 1: Input
    shape.draw_rect(pymupdf.Rect(80, 200, 180, 260))
    # Box 2: Model
    shape.draw_rect(pymupdf.Rect(230, 200, 330, 260))
    # Box 3: Loss
    shape.draw_rect(pymupdf.Rect(380, 200, 480, 260))
    # Connectors
    shape.draw_line(pymupdf.Point(180, 230), pymupdf.Point(230, 230))
    shape.draw_line(pymupdf.Point(330, 230), pymupdf.Point(380, 230))
    shape.finish(color=(0.2, 0.4, 0.8), fill=(0.92, 0.95, 1.0), width=2)
    shape.commit()

    page3.insert_text((105, 235), "Input (x)", fontsize=10, fontname="helv")
    page3.insert_text((250, 235), "Model f(x)", fontsize=10, fontname="helv")
    page3.insert_text((405, 235), "Loss L(y, y^)", fontsize=10, fontname="helv")
    page3.insert_text((180, 290), "Figure 1.1: Canonical Supervised Learning Pipeline", fontsize=10, fontname="helv")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    doc.close()
    print(f"Sample PDF created at: {output_path}")

if __name__ == "__main__":
    create_sample_pdf(str(Path(__file__).parent / "sample_textbook.pdf"))
