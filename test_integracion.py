"""Cinco pruebas con server.py y una copia de la base entregada, sin APIs."""
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
BASE=Path(__file__).resolve().parent

class ModeloSimulado:
    def __call__(self,messages):
        if messages[-1]['role']=='tool':
            data=json.loads(messages[-1]['content']);ident=data['muestra'][0]['id']
            return {'role':'assistant','content':f"Borrador de prueba: {data['total']} consultas [ID {ident}]."}
        return {'role':'assistant','tool_calls':[{'function':{'name':'resumir_historial','arguments':{}}}]}

class IntegracionServidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.original=BASE/'datos/yachaybot.db'
        cls.hash=hashlib.sha256(cls.original.read_bytes()).hexdigest();cls.db=Path(cls.tmp.name)/'yachaybot.db'
        src=sqlite3.connect('file:'+str(cls.original)+'?mode=ro',uri=True);dst=sqlite3.connect(cls.db);src.backup(dst);src.close();dst.close()
        cls.env=patch.dict(os.environ,{'YACHAYBOT_DATA_DIR':cls.tmp.name,'YACHAYBOT_NO_DESCARGAR_VOZ':'1','YACHAYBOT_TOKEN':'','GROQ_API_KEY':''});cls.env.start()
        spec=importlib.util.spec_from_file_location('yachaybot_integracion',BASE/'server.py');cls.server=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.server)
        cls.server.app.testing=True;cls.server.app.config['AGENTE_MODELO']=ModeloSimulado();cls.client=cls.server.app.test_client()
    @classmethod
    def tearDownClass(cls):cls.env.stop();cls.tmp.cleanup()
    def test_INT01_panel_enlace(self):
        r=self.client.get('/dashboard?dias=0');self.assertEqual(r.status_code,200);self.assertIn('/agente',r.get_data(as_text=True))
    def test_INT02_pagina_agente(self):self.assertEqual(self.client.get('/agente').status_code,200)
    def test_INT03_consulta_historial(self):
        r=self.client.post('/api/agente',json={'solicitud':'Resume consultas','todo_historial':True})
        self.assertEqual(r.status_code,200)
        with sqlite3.connect(self.db) as c:n=c.execute('select count(*) from interacciones').fetchone()[0]
        self.assertEqual(r.json['resumen']['total'],n);self.assertTrue(r.json['traza'])
    def test_INT04_filtro_matematica(self):
        r=self.client.post('/api/agente',json={'solicitud':'Resume Matemática','todo_historial':True,'tema':'Matemática'})
        with sqlite3.connect(self.db) as c:n=c.execute('select count(*) from interacciones where tema=?',('Matemática',)).fetchone()[0]
        self.assertEqual(r.status_code,200);self.assertEqual(r.json['resumen']['total'],n)
    def test_INT05_base_original_intacta(self):self.assertEqual(hashlib.sha256(self.original.read_bytes()).hexdigest(),self.hash)

if __name__=='__main__':unittest.main(verbosity=2)
