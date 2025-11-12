































#include "Python.h"

#include "libImaging/Imaging.h"

#include "libImaging/Bit.h"
#include "libImaging/Bcn.h"
#include "libImaging/Gif.h"
#include "libImaging/Raw.h"
#include "libImaging/Sgi.h"





typedef struct {
    PyObject_HEAD int (*decode)(
        Imaging im, ImagingCodecState state, uint8_t *buffer, Py_ssize_t bytes);
    int (*cleanup)(ImagingCodecState state);
    struct ImagingCodecStateInstance state;
    Imaging im;
    PyObject *lock;
    int pulls_fd;
} ImagingDecoderObject;

static PyTypeObject ImagingDecoderType;

static ImagingDecoderObject *
PyImaging_DecoderNew(int contextsize) {
    ImagingDecoderObject *decoder;
    void *context;

    if (PyType_Ready(&ImagingDecoderType) < 0) {
        return NULL;
    }

    decoder = PyObject_New(ImagingDecoderObject, &ImagingDecoderType);
    if (decoder == NULL) {
        return NULL;
    }


    memset(&decoder->state, 0, sizeof(decoder->state));


    if (contextsize > 0) {
        context = (void *)calloc(1, contextsize);
        if (!context) {
            Py_DECREF(decoder);
            (void)ImagingError_MemoryError();
            return NULL;
        }
    } else {
        context = 0;
    }


    decoder->state.context = context;


    decoder->lock = NULL;
    decoder->im = NULL;


    decoder->cleanup = NULL;



    decoder->pulls_fd = 0;

    return decoder;
}

static void
_dealloc(ImagingDecoderObject *decoder) {
    if (decoder->cleanup) {
        decoder->cleanup(&decoder->state);
    }
    free(decoder->state.buffer);
    free(decoder->state.context);
    Py_XDECREF(decoder->lock);
    Py_XDECREF(decoder->state.fd);
    PyObject_Del(decoder);
}

static PyObject *
_decode(ImagingDecoderObject *decoder, PyObject *args) {
    Py_buffer buffer;
    int status;
    ImagingSectionCookie cookie;

    if (!PyArg_ParseTuple(args, "y*", &buffer)) {
        return NULL;
    }

    if (!decoder->pulls_fd) {
        ImagingSectionEnter(&cookie);
    }

    status = decoder->decode(decoder->im, &decoder->state, buffer.buf, buffer.len);

    if (!decoder->pulls_fd) {
        ImagingSectionLeave(&cookie);
    }

    PyBuffer_Release(&buffer);
    return Py_BuildValue("ii", status, decoder->state.errcode);
}

static PyObject *
_decode_cleanup(ImagingDecoderObject *decoder, PyObject *args) {
    int status = 0;

    if (decoder->cleanup) {
        status = decoder->cleanup(&decoder->state);
    }

    return Py_BuildValue("i", status);
}

extern Imaging
PyImaging_AsImaging(PyObject *op);

static PyObject *
_setimage(ImagingDecoderObject *decoder, PyObject *args) {
    PyObject *op;
    Imaging im;
    ImagingCodecState state;
    int x0, y0, x1, y1;

    x0 = y0 = x1 = y1 = 0;


    if (!PyArg_ParseTuple(args, "O|(iiii)", &op, &x0, &y0, &x1, &y1)) {
        return NULL;
    }
    im = PyImaging_AsImaging(op);
    if (!im) {
        return NULL;
    }

    decoder->im = im;

    state = &decoder->state;


    if (x0 == 0 && x1 == 0) {
        state->xsize = im->xsize;
        state->ysize = im->ysize;
    } else {
        state->xoff = x0;
        state->yoff = y0;
        state->xsize = x1 - x0;
        state->ysize = y1 - y0;
    }

    if (state->xsize <= 0 || state->xsize + state->xoff > (int)im->xsize ||
        state->ysize <= 0 || state->ysize + state->yoff > (int)im->ysize) {
        PyErr_SetString(PyExc_ValueError, "tile cannot extend outside image");
        return NULL;
    }


    if (state->bits > 0) {
        if (!state->bytes) {
            if (state->xsize > ((INT_MAX / state->bits) - 7)) {
                return ImagingError_MemoryError();
            }
            state->bytes = (state->bits * state->xsize + 7) / 8;
        }

        state->buffer = (uint8_t *)calloc(1, state->bytes);
        if (!state->buffer) {
            return ImagingError_MemoryError();
        }
    }



    Py_INCREF(op);
    Py_XDECREF(decoder->lock);
    decoder->lock = op;

    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject *
_setfd(ImagingDecoderObject *decoder, PyObject *args) {
    PyObject *fd;
    ImagingCodecState state;

    if (!PyArg_ParseTuple(args, "O", &fd)) {
        return NULL;
    }

    state = &decoder->state;

    Py_XINCREF(fd);
    state->fd = fd;

    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject *
_get_pulls_fd(ImagingDecoderObject *decoder, void *closure) {
    return PyBool_FromLong(decoder->pulls_fd);
}

static struct PyMethodDef methods[] = {
    {"decode", (PyCFunction)_decode, METH_VARARGS},
    {"cleanup", (PyCFunction)_decode_cleanup, METH_VARARGS},
    {"setimage", (PyCFunction)_setimage, METH_VARARGS},
    {"setfd", (PyCFunction)_setfd, METH_VARARGS},
    {NULL, NULL}
};

static struct PyGetSetDef getseters[] = {
    {"pulls_fd",
     (getter)_get_pulls_fd,
     NULL,
     "True if this decoder expects to pull from self.fd itself.",
     NULL},
    {NULL, NULL, NULL, NULL, NULL}
};

static PyTypeObject ImagingDecoderType = {
    PyVarObject_HEAD_INIT(NULL, 0) "ImagingDecoder",
    sizeof(ImagingDecoderObject),
    0,

    (destructor)_dealloc,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    Py_TPFLAGS_DEFAULT,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    methods,
    0,
    getseters,
};



int
get_unpacker(ImagingDecoderObject *decoder, const char *mode, const char *rawmode) {
    int bits;
    ImagingShuffler unpack;

    unpack = ImagingFindUnpacker(mode, rawmode, &bits);
    if (!unpack) {
        Py_DECREF(decoder);
        PyErr_SetString(PyExc_ValueError, "unknown raw mode for given image mode");
        return -1;
    }

    decoder->state.shuffle = unpack;
    decoder->state.bits = bits;

    return 0;
}





PyObject *
PyImaging_BitDecoderNew(PyObject *self, PyObject *args) {
    ImagingDecoderObject *decoder;

    char *mode;
    int bits = 8;
    int pad = 8;
    int fill = 0;
    int sign = 0;
    int ystep = 1;
    if (!PyArg_ParseTuple(args, "s|iiiii", &mode, &bits, &pad, &fill, &sign, &ystep)) {
        return NULL;
    }

    if (strcmp(mode, "F") != 0) {
        PyErr_SetString(PyExc_ValueError, "bad image mode");
        return NULL;
    }

    decoder = PyImaging_DecoderNew(sizeof(BITSTATE));
    if (decoder == NULL) {
        return NULL;
    }

    decoder->decode = ImagingBitDecode;

    decoder->state.ystep = ystep;

    ((BITSTATE *)decoder->state.context)->bits = bits;
    ((BITSTATE *)decoder->state.context)->pad = pad;
    ((BITSTATE *)decoder->state.context)->fill = fill;
    ((BITSTATE *)decoder->state.context)->sign = sign;

    return (PyObject *)decoder;
}





PyObject *
PyImaging_BcnDecoderNew(PyObject *self, PyObject *args) {
    ImagingDecoderObject *decoder;

    char *mode;
    char *actual;
    int n = 0;
    char *pixel_format = "";
    if (!PyArg_ParseTuple(args, "si|s", &mode, &n, &pixel_format)) {
        return NULL;
    }

    switch (n) {
        case 1:
        case 2:
        case 3:
        case 7:
            actual = "RGBA";
            break;
        case 4:
            actual = "L";
            break;
        case 5:
        case 6:
            actual = "RGB";
            break;
        default:
            PyErr_SetString(PyExc_ValueError, "block compression type unknown");
            return NULL;
    }

    if (strcmp(mode, actual) != 0) {
        PyErr_SetString(PyExc_ValueError, "bad image mode");
        return NULL;
    }

    decoder = PyImaging_DecoderNew(sizeof(char *));
    if (decoder == NULL) {
        return NULL;
    }

    decoder->decode = ImagingBcnDecode;
    decoder->state.state = n;
    ((BCNSTATE *)decoder->state.context)->pixel_format = pixel_format;

    return (PyObject *)decoder;
}





PyObject *
PyImaging_FliDecoderNew(PyObject *self, PyObject *args) {
    ImagingDecoderObject *decoder;

    decoder = PyImaging_DecoderNew(0);
    if (decoder == NULL) {
        return NULL;
    }

    decoder->decode = ImagingFliDecode;

    return (PyObject *)decoder;
}





PyObject *
PyImaging_GifDecoderNew(PyObject *self, PyObject *args) {
    ImagingDecoderObject *decoder;

    char *mode;
    int bits = 8;
    int interlace = 0;
    int transparency = -1;
    if (!PyArg_ParseTuple(args, "s|iii", &mode, &bits, &interlace, &transparency)) {
        return NULL;
    }

    if (strcmp(mode, "L") != 0 && strcmp(mode, "P") != 0) {
        PyErr_SetString(PyExc_ValueError, "bad image mode");
        return NULL;
    }

    decoder = PyImaging_DecoderNew(sizeof(GIFDECODERSTATE));
    if (decoder == NULL) {
        return NULL;
    }

    decoder->decode = ImagingGifDecode;

    ((GIFDECODERSTATE *)decoder->state.context)->bits = bits;
    ((GIFDECODERSTATE *)decoder->state.context)->interlace = interlace;
    ((GIFDECODERSTATE *)decoder->state.context)->transparency = transparency;

    return (PyObject *)decoder;
}





PyObject *
PyImaging_HexDecoderNew(PyObject *self, PyObject *args) {
    ImagingDecoderObject *decoder;

    char *mode;
    char *rawmode;
    if (!PyArg_ParseTuple(args, "ss", &mode, &rawmode)) {
        return NULL;
    }

    decoder = PyImaging_DecoderNew(0);
    if (decoder == NULL) {
        return NULL;
    }

    if (get_unpacker(decoder, mode, rawmode) < 0) {
        return NULL;
    }

    decoder->decode = ImagingHexDecode;

    return (PyObject *)decoder;
}







#include "libImaging/TiffDecode.h"

#include <string.h>

PyObject *
PyImaging_LibTiffDecoderNew(PyObject *self, PyObject *args) {
    ImagingDecoderObject *decoder;
    char *mode;
    char *rawmode;
    char *compname;
    int fp;
    uint32_t ifdoffset;

    if (!PyArg_ParseTuple(args, "sssiI", &mode, &rawmode, &compname, &fp, &ifdoffset)) {
        return NULL;
    }

    TRACE(("new tiff decoder %s\n", compname));

    decoder = PyImaging_DecoderNew(sizeof(TIFFSTATE));
    if (decoder == NULL) {
        return NULL;
    }

    if (get_unpacker(decoder, mode, rawmode) < 0) {
        return NULL;
    }

    if (!ImagingLibTiffInit(&decoder->state, fp, ifdoffset)) {
        Py_DECREF(decoder);
        PyErr_SetString(PyExc_RuntimeError, "tiff codec initialization failed");
        return NULL;
    }

    decoder->decode = ImagingLibTiffDecode;

    return (PyObject *)decoder;
}







PyObject *
PyImaging_PackbitsDecoderNew(PyObject *self, PyObject *args) {
    ImagingDecoderObject *decoder;

    char *mode;
    char *rawmode;
    if (!PyArg_ParseTuple(args, "ss", &mode, &rawmode)) {
        return NULL;
    }

    decoder = PyImaging_DecoderNew(0);
    if (decoder == NULL) {
        return NULL;
    }

    if (get_unpacker(decoder, mode, rawmode) < 0) {
        return NULL;
    }

    decoder->decode = ImagingPackbitsDecode;

    return (PyObject *)decoder;
}





PyObject *
PyImaging_PcdDecoderNew(PyObject *self, PyObject *args) {
    ImagingDecoderObject *decoder;

    decoder = PyImaging_DecoderNew(0);
    if (decoder == NULL) {
        return NULL;
    }


    if (get_unpacker(decoder, "RGB", "YCC;P") < 0) {
        return NULL;
    }

    decoder->decode = ImagingPcdDecode;

    return (PyObject *)decoder;
}





PyObject *
PyImaging_PcxDecoderNew(PyObject *self, PyObject *args) {
    ImagingDecoderObject *decoder;

    char *mode;
    char *rawmode;
    int stride;
    if (!PyArg_ParseTuple(args, "ssi", &mode, &rawmode, &stride)) {
        return NULL;
    }

    decoder = PyImaging_DecoderNew(0);
    if (decoder == NULL) {
        return NULL;
    }

    if (get_unpacker(decoder, mode, rawmode) < 0) {
        return NULL;
    }

    decoder->state.bytes = stride;

    decoder->decode = ImagingPcxDecode;

    return (PyObject *)decoder;
}





PyObject *
PyImaging_RawDecoderNew(PyObject *self, PyObject *args) {
    ImagingDecoderObject *decoder;

    char *mode;
    char *rawmode;
    int stride = 0;
    int ystep = 1;
    if (!PyArg_ParseTuple(args, "ss|ii", &mode, &rawmode, &stride, &ystep)) {
        return NULL;
    }

    decoder = PyImaging_DecoderNew(sizeof(RAWSTATE));
    if (decoder == NULL) {
        return NULL;
    }

    if (get_unpacker(decoder, mode, rawmode) < 0) {
        return NULL;
    }

    decoder->decode = ImagingRawDecode;

    decoder->state.ystep = ystep;

    ((RAWSTATE *)decoder->state.context)->stride = stride;

    return (PyObject *)decoder;
}





PyObject *
PyImaging_SgiRleDecoderNew(PyObject *self, PyObject *args) {
    ImagingDecoderObject *decoder;

    char *mode;
    char *rawmode;
    int ystep = 1;
    int bpc = 1;
    if (!PyArg_ParseTuple(args, "ss|ii", &mode, &rawmode, &ystep, &bpc)) {
        return NULL;
    }

    decoder = PyImaging_DecoderNew(sizeof(SGISTATE));
    if (decoder == NULL) {
        return NULL;
    }

    if (get_unpacker(decoder, mode, rawmode) < 0) {
        return NULL;
    }

    decoder->pulls_fd = 1;
    decoder->decode = ImagingSgiRleDecode;
    decoder->state.ystep = ystep;

    ((SGISTATE *)decoder->state.context)->bpc = bpc;

    return (PyObject *)decoder;
}





PyObject *
PyImaging_SunRleDecoderNew(PyObject *self, PyObject *args) {
    ImagingDecoderObject *decoder;

    char *mode;
    char *rawmode;
    if (!PyArg_ParseTuple(args, "ss", &mode, &rawmode)) {
        return NULL;
    }

    decoder = PyImaging_DecoderNew(0);
    if (decoder == NULL) {
        return NULL;
    }

    if (get_unpacker(decoder, mode, rawmode) < 0) {
        return NULL;
    }

    decoder->decode = ImagingSunRleDecode;

    return (PyObject *)decoder;
}





PyObject *
PyImaging_TgaRleDecoderNew(PyObject *self, PyObject *args) {
    ImagingDecoderObject *decoder;

    char *mode;
    char *rawmode;
    int ystep = 1;
    int depth = 8;
    if (!PyArg_ParseTuple(args, "ss|ii", &mode, &rawmode, &ystep, &depth)) {
        return NULL;
    }

    decoder = PyImaging_DecoderNew(0);
    if (decoder == NULL) {
        return NULL;
    }

    if (get_unpacker(decoder, mode, rawmode) < 0) {
        return NULL;
    }

    decoder->decode = ImagingTgaRleDecode;

    decoder->state.ystep = ystep;
    decoder->state.count = depth / 8;

    return (PyObject *)decoder;
}





PyObject *
PyImaging_XbmDecoderNew(PyObject *self, PyObject *args) {
    ImagingDecoderObject *decoder;

    decoder = PyImaging_DecoderNew(0);
    if (decoder == NULL) {
        return NULL;
    }

    if (get_unpacker(decoder, "1", "1;R") < 0) {
        return NULL;
    }

    decoder->decode = ImagingXbmDecode;

    return (PyObject *)decoder;
}







#include "libImaging/ZipCodecs.h"

PyObject *
PyImaging_ZipDecoderNew(PyObject *self, PyObject *args) {
    ImagingDecoderObject *decoder;

    char *mode;
    char *rawmode;
    int interlaced = 0;
    if (!PyArg_ParseTuple(args, "ss|i", &mode, &rawmode, &interlaced)) {
        return NULL;
    }

    decoder = PyImaging_DecoderNew(sizeof(ZIPSTATE));
    if (decoder == NULL) {
        return NULL;
    }

    if (get_unpacker(decoder, mode, rawmode) < 0) {
        return NULL;
    }

    decoder->decode = ImagingZipDecode;
    decoder->cleanup = ImagingZipDecodeCleanup;

    ((ZIPSTATE *)decoder->state.context)->interlaced = interlaced;

    return (PyObject *)decoder;
}





















#include "libImaging/Jpeg.h"

PyObject *
PyImaging_JpegDecoderNew(PyObject *self, PyObject *args) {
    ImagingDecoderObject *decoder;

    char *mode;
    char *rawmode;
    char *jpegmode;
    int scale = 1;
    int draft = 0;

    if (!PyArg_ParseTuple(args, "ssz|ii", &mode, &rawmode, &jpegmode, &scale, &draft)) {
        return NULL;
    }

    if (!jpegmode) {
        jpegmode = "";
    }

    decoder = PyImaging_DecoderNew(sizeof(JPEGSTATE));
    if (decoder == NULL) {
        return NULL;
    }




    if (ImagingJpegUseJCSExtensions() && strcmp(rawmode, "RGB") == 0) {
        rawmode = "RGBX";
    }

    if (get_unpacker(decoder, mode, rawmode) < 0) {
        return NULL;
    }

    decoder->decode = ImagingJpegDecode;
    decoder->cleanup = ImagingJpegDecodeCleanup;

    strncpy(((JPEGSTATE *)decoder->state.context)->rawmode, rawmode, 8);
    strncpy(((JPEGSTATE *)decoder->state.context)->jpegmode, jpegmode, 8);

    ((JPEGSTATE *)decoder->state.context)->scale = scale;
    ((JPEGSTATE *)decoder->state.context)->draft = draft;

    return (PyObject *)decoder;
}








#include "libImaging/Jpeg2K.h"

PyObject *
PyImaging_Jpeg2KDecoderNew(PyObject *self, PyObject *args) {
    ImagingDecoderObject *decoder;
    JPEG2KDECODESTATE *context;

    char *mode;
    char *format;
    OPJ_CODEC_FORMAT codec_format;
    int reduce = 0;
    int layers = 0;
    int fd = -1;
    PY_LONG_LONG length = -1;

    if (!PyArg_ParseTuple(
            args, "ss|iiiL", &mode, &format, &reduce, &layers, &fd, &length)) {
        return NULL;
    }

    if (strcmp(format, "j2k") == 0) {
        codec_format = OPJ_CODEC_J2K;
    } else if (strcmp(format, "jpt") == 0) {
        codec_format = OPJ_CODEC_JPT;
    } else if (strcmp(format, "jp2") == 0) {
        codec_format = OPJ_CODEC_JP2;
    } else {
        return NULL;
    }

    decoder = PyImaging_DecoderNew(sizeof(JPEG2KDECODESTATE));
    if (decoder == NULL) {
        return NULL;
    }

    decoder->pulls_fd = 1;
    decoder->decode = ImagingJpeg2KDecode;
    decoder->cleanup = ImagingJpeg2KDecodeCleanup;

    context = (JPEG2KDECODESTATE *)decoder->state.context;

    context->fd = fd;
    context->length = (off_t)length;
    context->format = codec_format;
    context->reduce = reduce;
    context->layers = layers;

    return (PyObject *)decoder;
}
