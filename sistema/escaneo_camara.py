import cv2


def _intentar(detector, imagen):
    if imagen is None or imagen.size == 0:
        return None
    try:
        texto, _, _ = detector.detectAndDecode(imagen)
        return texto or None
    except cv2.error:
        return None


def _leer(detector, frame, reforzado=False):
    """Busca QR en todo el fotograma, sin limitar la lectura a una zona central."""
    if frame is None or frame.size == 0:
        return None

    # Primero se prueba la imagen completa para conservar detalle y rapidez.
    texto = _intentar(detector, frame)
    if texto:
        return texto

    # El procesamiento adicional se hace solo periódicamente para no ralentizar
    # la vista previa. Todas las operaciones abarcan el fotograma completo.
    if not reforzado:
        return None

    gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    texto = _intentar(detector, gris)
    if texto:
        return texto

    # La detección múltiple puede ayudar con algunos QR y no impone una región.
    try:
        ok, textos, _, _ = detector.detectAndDecodeMulti(frame)
        if ok and textos:
            for texto in textos:
                if texto:
                    return texto
    except (cv2.error, ValueError):
        pass

    # Refuerzo ocasional para QR mostrados en la pantalla de un teléfono.
    grande = cv2.resize(gris, None, fx=1.25, fy=1.25, interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    mejor = clahe.apply(grande)
    texto = _intentar(detector, mejor)
    if texto:
        return texto

    try:
        _, umbral = cv2.threshold(mejor, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        texto = _intentar(detector, umbral)
        if texto:
            return texto
    except cv2.error:
        pass

    return None


def escanear(titulo="Escanear QR (ESC o X para cancelar)"):
    """Abre la cámara y devuelve el primer QR leído. ESC o cerrar la ventana cancela."""
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return None

    # Resolución equilibrada para que la vista y el análisis sean más ágiles.
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
    try:
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
    except Exception:
        pass

    detector = cv2.QRCodeDetector()
    texto = None
    frame_n = 0

    try:
        cv2.namedWindow(titulo, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(titulo, 800, 450)

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_n += 1

            # Vista limpia: no hay recuadro ni zona obligatoria para colocar el QR.
            vista = frame.copy()
            cv2.putText(vista, "Muestra el codigo QR en cualquier parte de la imagen",
                        (16, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.62,
                        (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(vista, "ESC o cierra la ventana para cancelar",
                        (16, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.50,
                        (255, 255, 255), 1, cv2.LINE_AA)
            cv2.imshow(titulo, vista)

            # Lectura frecuente y refuerzo de imagen cada 6 fotogramas.
            if frame_n % 2 == 0:
                texto = _leer(detector, frame, reforzado=(frame_n % 6 == 0))
                if texto:
                    break

            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key in (ord('x'), ord('X')):
                break
            try:
                if cv2.getWindowProperty(titulo, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break

    finally:
        cap.release()
        try:
            cv2.destroyWindow(titulo)
        except cv2.error:
            cv2.destroyAllWindows()
        cv2.waitKey(1)

    return texto or None
