
#include <Python.h>
#include <structmember.h>

#include "Coder.h"
#include "Decoder.h"
#include "CodingException.h"
#include <iostream>
#include <sstream>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <vector>

typedef struct {
	PyObject_HEAD
	int dataBlocks;
	int parityBlocks;
	int leftDegree;
} FileCoder;

static void FileCoder_dealloc(FileCoder *self) {
	self->ob_type->tp_free((PyObject*)self);
}

static PyObject *FileCoder_new(PyTypeObject *type, PyObject *args, 
		PyObject *kwds) {
	FileCoder *self;

	self = (FileCoder *)type->tp_alloc(type, 0);
	self->leftDegree = 0;
	return (PyObject *)self;
}

static int FileCoder_init(FileCoder *self, PyObject *args, PyObject *kwds) {

	static char *kwlist[] = {"dataBlocks", "parityBlocks", "leftDegree", NULL};
	if (!PyArg_ParseTupleAndKeywords(args, kwds, "iii", kwlist,
				&self->dataBlocks,
				&self->parityBlocks, &self->leftDegree))
		return -1;

	if (self->leftDegree == 0) {
		self->leftDegree = 7;
	}

	return 0;
}

static PyObject *FileCoder_codeData(FileCoder *self, PyObject *args) {
	
	char *filename = NULL, *stem = NULL;
	if (!PyArg_ParseTuple(args, "ss", &filename, &stem)) {
		return NULL;
	}

	Coder coder(self->dataBlocks, self->parityBlocks, self->leftDegree);
	
	int fd;
	if ((fd = open(filename, O_RDONLY, 0)) == -1) {
		std::cerr << "unable to open " << filename << std::endl;
		exit(-1);
	}
	struct stat statbuf;
	if (fstat(fd, &statbuf) != 0) {
		std::cerr << "unable to stat " << filename << std::endl;
		exit(-1);
	}
	int dataLen = statbuf.st_size;
	//char data[dataLen];
	char *data = (char*)calloc(dataLen, sizeof(char));
	if (data == NULL) {
		printf("couldn't allocate memory for file read\n");
		exit(-1);
	}

	int bytesread=0;
	do {
		bytesread += read(fd, data+bytesread, dataLen);
	} while (bytesread < dataLen);
	close(fd);

	// code the data
	CodedBlocks coded;
	try {
		coded = coder.codeData(data, dataLen);
	} catch (CodingException& ce) {
		std::cerr << ce.toString() << std::endl;
		// XXX: was 'return -1'
		Py_INCREF(Py_None);
		return Py_None;
	}

	std::vector<std::string> stemfiles;
	// write the coded data to files
	for (int i=0; i<coded.numBlocks; i++) {
		char newfile[255];
		sprintf(newfile,"%s-%04d",stem,i);
		if ((fd = creat(newfile, 0666)) < 0) {
			std::cerr << "unable to open " << newfile << std::endl;
			Py_INCREF(Py_None);
			return Py_None;
		}
		int byteswritten = 0;
		while (byteswritten < coded.blockLen) {
			int ret = write(fd, coded.blocks[i]+byteswritten, 
					coded.blockLen-byteswritten);
			byteswritten += ret;
			if (ret < 0) {
				std::cerr << "unable to write to " << newfile << std::endl;
				Py_INCREF(Py_None);
				close(fd);
				return Py_None;
			}
		}
		stemfiles.push_back(newfile);
		close(fd);
	}
	close(fd);

	coded.freeBlocks();
	PyObject *t = PyList_New(stemfiles.size());
	for (unsigned i=0; i<stemfiles.size(); i++) {
		PyObject *o = Py_BuildValue("s",stemfiles[i].c_str());
		PyList_SetItem(t, i, o); 
	}
	return t;
}

static PyMethodDef FileCoder_methods[] = {
	{"codeData", (PyCFunction)FileCoder_codeData, METH_VARARGS,
		"codes some a file" },
	{NULL}
};

static PyTypeObject FileCoderType = {
	PyObject_HEAD_INIT(NULL)
	0,                            /* ob_size */
	"filecoder.c_Coder",          /* tp_name */
	sizeof(FileCoder),            /* tp_basicsize */
	0,                            /* tp_itemsize */
	(destructor)FileCoder_dealloc,/* tp_dealloc */
	0,                            /* tp_print */
	0,                            /* tp_getattr */
	0,                            /* tp_setattr */
	0,                            /* tp_compare */
	0,                            /* tp_repr */
	0,                            /* tp_as_number */
	0,                            /* tp_as_sequence */
	0,                            /* tp_as_mapping */
	0,                            /* tp_hash */
	0,                            /* tp_call */
	0,                            /* tp_str */
	0,                            /* tp_getattro */
	0,                            /* tp_setattro */
	0,                            /* tp_as_buffer */
	Py_TPFLAGS_DEFAULT,           /* tp_flags */
	"FileCoder object",           /* tp_doc */
	0,                            /* tp_traverse */
	0,                            /* tp_clear */
	0,                            /* tp_richcompare */
	0,                            /* tp_weaklistoffset */
	0,                            /* tp_iter */
	0,                            /* tp_iternext */
	FileCoder_methods,            /* tp_methods */
	0,                            /* tp_members */
	0,                            /* tp_getset */
	0,                            /* tp_base */
	0,                            /* tp_dict */
	0,                            /* tp_descr_get */
	0,                            /* tp_descr_set */
	0,                            /* tp_dictoffset */
	(initproc)FileCoder_init,     /* tp_init */
	0,                            /* tp_alloc */
	FileCoder_new,                /* tp_new */
};


typedef struct {
	PyObject_HEAD
	PyObject *destFile;
	int blockLen;
	int dataBlocks;
	int parityBlocks;
	int leftDegree;
	Decoder *decoder;
	char *recoveredData;
} FileDecoder;

static void FileDecoder_dealloc(FileDecoder *self) {
	if (self->decoder != NULL) { // XXX: could be trouble -- need to refcount
		delete self->decoder;
	}
	if (self->recoveredData != NULL) { // XXX: could be trouble 
		                               //      -- need to refcount
		delete self->recoveredData;
	}
	Py_XDECREF(self->destFile);
	self->ob_type->tp_free((PyObject*)self);
}

static PyObject *FileDecoder_new(PyTypeObject *type, PyObject *args, 
		PyObject *kwds) {
	FileDecoder *self;

	self = (FileDecoder *)type->tp_alloc(type, 0);
	if (self != NULL) {
		self->destFile = PyString_FromString("");
		if (self->destFile == NULL) {
			Py_DECREF(self);
			return NULL;
		}
	}
	self->decoder = NULL;
	self->recoveredData = NULL;
	self->leftDegree = 0;
	return (PyObject *)self;
}

static int FileDecoder_init(FileDecoder *self, PyObject *args, PyObject *kwds) {
	PyObject *destFile=NULL, *tmp=NULL;

	static char *kwlist[] = {"destFile", "dataBlocks", "parityBlocks", 
		"leftDegree", NULL};
	if (!PyArg_ParseTupleAndKeywords(args, kwds, "Siii", kwlist,
				&destFile, &self->dataBlocks,
				&self->parityBlocks, &self->leftDegree))
		return -1;

	if (destFile) {
		tmp = self->destFile;
		Py_INCREF(destFile);
		self->destFile = destFile;
		Py_DECREF(tmp);
	}

	if (self->leftDegree == 0) {
		self->leftDegree = 7;
	}

	return 0;
}

static PyObject *FileDecoder_done(FileDecoder *self) {
	PyObject *result;
	if (self->decoder == NULL || !self->decoder->done()) {
		result = Py_BuildValue("b", false);	
	} else {
		result = Py_BuildValue("b", true);	
	}
	return result;
}

static PyObject *FileDecoder_decodeData(FileDecoder *self, PyObject *args) {
	
	char *filename = NULL;
	if (!PyArg_ParseTuple(args, "s", &filename)) {
		return NULL;
	}
	int fd;
	if ((fd = open(filename, O_RDONLY, 0)) == -1) {
		std::cerr << "unable to open " << filename << std::endl;
		return NULL;
	}

	//std::cout << "successfully opened " << filename << std::endl;
	struct stat statbuf;
	if (fstat(fd, &statbuf) != 0) {
		std::cerr << "unable to stat " << filename << std::endl;
		return NULL;
	}
	int dataLen = statbuf.st_size;
	// XXX: make sure dataLen isn't too big.
	char *databuf = new char[dataLen];
	int bytesread=0;
	do {
		bytesread += read(fd, databuf, dataLen);
		// XXX: check for negative result from read;
	} while (bytesread < dataLen);
	close(fd);

	if (self->decoder == NULL) {
		self->blockLen = dataLen;
		self->decoder = new Decoder(self->blockLen, self->dataBlocks, 
				self->parityBlocks, self->leftDegree);
	}
	
	if (self->decoder->done()) return FileDecoder_done(self);

	int recDataLen = self->decoder->decodeData(self->recoveredData, databuf);
	if (recDataLen > 0) {
		int fd2;
		char* filename;
		filename = PyString_AsString(self->destFile);
		//std::cout << "recovered file: " << filename << std::endl;
		if ((fd2 = creat(filename, 0644)) == -1) {
			std::cout << "unable to open '" << filename 
				<< "' for writing" << std::endl;
		} else {
			int byteswritten=0;
			do {
				int res = write(fd2, self->recoveredData, recDataLen);
				// XXX: check for negative res;
				byteswritten += res;
			} while (byteswritten < recDataLen);
			delete self->recoveredData;
			self->recoveredData = NULL;
			close(fd2);
			PyObject *result;
			result = Py_BuildValue("b", true);	
			return result;
		}
	}
	return FileDecoder_done(self);
}

static PyMethodDef FileDecoder_methods[] = {
	{"decodeData", (PyCFunction)FileDecoder_decodeData, METH_VARARGS,
		"decodes some data" },
	{"done", (PyCFunction)FileDecoder_done, METH_NOARGS,
		"indicates when decoding is done" },
	{NULL}
};

static PyTypeObject FileDecoderType = {
	PyObject_HEAD_INIT(NULL)
	0,                            /* ob_size */
	"filecoder.c_Decoder",        /* tp_name */
	sizeof(FileDecoder),          /* tp_basicsize */
	0,                            /* tp_itemsize */
	(destructor)FileDecoder_dealloc,  /* tp_dealloc */
	0,                            /* tp_print */
	0,                            /* tp_getattr */
	0,                            /* tp_setattr */
	0,                            /* tp_compare */
	0,                            /* tp_repr */
	0,                            /* tp_as_number */
	0,                            /* tp_as_sequence */
	0,                            /* tp_as_mapping */
	0,                            /* tp_hash */
	0,                            /* tp_call */
	0,                            /* tp_str */
	0,                            /* tp_getattro */
	0,                            /* tp_setattro */
	0,                            /* tp_as_buffer */
	Py_TPFLAGS_DEFAULT,           /* tp_flags */
	"FileDecoder object",         /* tp_doc */
	0,                            /* tp_traverse */
	0,                            /* tp_clear */
	0,                            /* tp_richcompare */
	0,                            /* tp_weaklistoffset */
	0,                            /* tp_iter */
	0,                            /* tp_iternext */
	FileDecoder_methods,          /* tp_methods */
	0,                            /* tp_members */
	0,                            /* tp_getset */
	0,                            /* tp_base */
	0,                            /* tp_dict */
	0,                            /* tp_descr_get */
	0,                            /* tp_descr_set */
	0,                            /* tp_dictoffset */
	(initproc)FileDecoder_init,   /* tp_init */
	0,                            /* tp_alloc */
	FileDecoder_new,              /* tp_new */
};




static PyMethodDef module_methods[] = {
	    {NULL}  /* Sentinel */
};

#ifndef PyMODINIT_FUNC	/* declarations for DLL import/export */
#define PyMODINIT_FUNC void
#endif

PyMODINIT_FUNC initfilecoder(void) {
	PyObject *m;

	if (PyType_Ready(&FileDecoderType) < 0
			|| PyType_Ready(&FileCoderType) < 0)
		return;
	
	m = Py_InitModule3("filecoder", module_methods,
			"This module provides file coding/decoding.");
	
	if (m == NULL)
		return;
	
	Py_INCREF(&FileCoderType);
	PyModule_AddObject(m, "c_Coder", (PyObject *)&FileCoderType);
	Py_INCREF(&FileDecoderType);
	PyModule_AddObject(m, "c_Decoder", (PyObject *)&FileDecoderType);
}


