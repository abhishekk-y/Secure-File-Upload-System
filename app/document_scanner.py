"""Bounded document enhancement for images already validated by the upload pipeline."""
import io

import cv2
import numpy as np
from PIL import Image

cv2.setNumThreads(1)


def scan_document(raw, mime):
    """Return normalized bytes and a truthful processing description, never an AV verdict."""
    if mime not in ('image/png', 'image/jpeg'):
        raise ValueError('Document scanning requires a PNG or JPEG image.')
    with Image.open(io.BytesIO(raw)) as picture:
        if picture.width * picture.height > 16_000_000:
            raise ValueError('Document image exceeds 16 megapixels.')
        rgb = picture.convert('RGB')
        # Downsample before computer-vision work to bound processing and output dimensions.
        rgb.thumbnail((2000, 2000))
        source = np.array(rgb)
    if min(source.shape[:2]) < 64:
        raise ValueError('Document photos must be at least 64 pixels on each side.')
    gray = cv2.cvtColor(source, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    page = None
    area = gray.shape[0] * gray.shape[1]
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:10]:
        if cv2.contourArea(contour) < area * .20:
            continue
        polygon = cv2.approxPolyDP(contour, .02 * cv2.arcLength(contour, True), True)
        if len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        points = polygon.reshape(4, 2).astype(np.float32)
        # Sort around centroid, then start at the upper-left-like corner.
        center = points.mean(axis=0)
        points = points[np.argsort(np.arctan2(points[:, 1]-center[1], points[:, 0]-center[0]))]
        points = np.roll(points, -int(np.argmin(points.sum(axis=1))), axis=0)
        top_left, top_right, bottom_right, bottom_left = points
        width = int(max(np.linalg.norm(top_right-top_left), np.linalg.norm(bottom_right-bottom_left)))
        height = int(max(np.linalg.norm(bottom_left-top_left), np.linalg.norm(bottom_right-top_right)))
        if min(width, height) < 64:
            continue
        destination = np.float32([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]])
        transform = cv2.getPerspectiveTransform(points, destination)
        page = cv2.warpPerspective(gray, transform, (width, height))
        break
    detected = page is not None
    if page is None:
        page = gray
    cleaned = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(page)
    output = io.BytesIO()
    Image.fromarray(cleaned).save(output, format='PNG' if mime == 'image/png' else 'JPEG')
    result = output.getvalue()
    if len(result) > 5 * 1024 * 1024:
        raise ValueError('Processed document exceeds 5 MiB.')
    detail = 'Page detected, straightened and enhanced.' if detected else 'No clear page boundary found; full image enhanced without cropping.'
    return result, detail
