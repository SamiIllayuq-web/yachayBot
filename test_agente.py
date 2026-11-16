"""Pruebas reproducibles sin credenciales ni servicios de inferencia externos.
Ejecutar: python -m unittest -v test_agente.py
"""
import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import requests
from flask import Flask
from agente_docente import AgentError, ModeloHTTP, ejecutar, leer_resumen, registrar_agente, validar

BASE=Path(__file__).resolve().parent
def llamada(name="resumir_historial",args=None):
    return {"role":"assistant","tool_calls":[{"id":"call_1","type":"function","function":{"name":name,"arguments":args if args is not None else {}}}]}
class Secuencia:
    def __init__(self,*responses):self.responses=list(responses);self.inputs=[]
    def __call__(self,messages):
        self.inputs.append(json.loads(json.dumps(messages)))
        if not self.responses:raise AssertionError('Llamadas de más al modelo simulado')
        item=self.responses.pop(0)
        if isinstance(item,Exception):raise item
        return item

class PruebasAgente(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'datos.db'
        with sqlite3.connect(self.path) as c:
            c.execute('CREATE TABLE interacciones(id INTEGER PRIMARY KEY,fecha TEXT,pregunta TEXT,tema TEXT)')
            c.executemany('INSERT INTO interacciones VALUES(?,?,?,?)',[
                (1,'2026-08-18T09:00:00','¿Qué es una fracción?','Matemática'),
                (2,'2026-08-18T23:59:59','¿Cómo sumar?','Matemática'),
                (3,'2026-08-20T12:00:00','¿Qué es un sustantivo?','Comunicación'),
                (4,'2026-08-21T00:00:00','Hola','Conversación')])
        self.app=Flask(__name__,template_folder=str(BASE/'templates'));self.app.testing=True
        registrar_agente(self.app,lambda:str(self.path));self.app.config['AGENTE_LOG']=str(Path(self.tmp.name)/'log.jsonl')
        self.c=self.app.test_client();self.payload=dict(solicitud='Resume las consultas',todo_historial=True)
        self.env=patch.dict(os.environ,{'YACHAYBOT_TOKEN':''});self.env.start();self.addCleanup(self.env.stop)
    def post(self,payload=None):return self.c.post('/api/agente',json=self.payload if payload is None else payload)
    def good_model(self,text='Hay 4 consultas. Ejemplo: fracciones [ID 1].'):
        model=Secuencia(llamada(),{'role':'assistant','content':text});self.app.config['AGENTE_MODELO']=model;return model
    def error(self,model,code,status=502):
        self.app.config['AGENTE_MODELO']=model;r=self.post();self.assertEqual(r.status_code,status);self.assertEqual(r.json['codigo'],code)
    def test_01_interfaz_y_enlace(self):
        self.assertEqual(self.c.get('/agente').status_code,200)
        self.assertIn(b'Preparar borrador',self.c.get('/agente').data)
    def test_02_informe_herramienta_y_citas(self):
        model=self.good_model();r=self.post();self.assertEqual(r.status_code,200)
        self.assertEqual(r.json['resumen']['total'],4);self.assertEqual(r.json['traza'][0]['herramienta'],'resumir_historial')
        self.assertTrue(any(m['role']=='tool' for m in model.inputs[1]))
        self.assertIn('[ID 1]',r.json['respuesta'])
    def test_03_filtro_tema(self):
        self.good_model();self.payload['tema']='Matemática';r=self.post()
        self.assertEqual(r.json['resumen']['total'],2)
    def test_04_fechas_incluyen_ultimo_dia(self):
        self.good_model();self.payload.update(todo_historial=False,desde='2026-08-18',hasta='2026-08-18')
        self.assertEqual(self.post().json['resumen']['total'],2)
    def test_05_pide_periodo(self):
        r=self.post({'solicitud':'Resume las consultas'});self.assertEqual(r.status_code,422)
    def test_06_fechas_invertidas(self):
        self.payload.update(todo_historial=False,desde='2026-08-20',hasta='2026-08-18');self.assertEqual(self.post().status_code,400)
    def test_07_sin_datos(self):
        self.app.config['AGENTE_MODELO']=Secuencia(llamada());self.payload['tema']='Inexistente'
        r=self.post();self.assertEqual(r.status_code,200);self.assertEqual(r.json['estado'],'sin_datos')
    def test_08_actividades_piden_grado(self):
        self.payload['tarea']='actividades';self.assertEqual(self.post().status_code,422)
    def test_09_actividades_con_solucionario(self):
        self.good_model('Borrador de 2 ejercicios para cuarto de primaria, sobre consultas [ID 1].\n1. Representa 1/2.\n2. Calcula 1/2+1/2.\nSolucionario\n1. Una mitad.\n2. 1.')
        self.payload.update(tarea='actividades',grado='Cuarto de primaria',cantidad=2)
        r=self.post();self.assertEqual(r.status_code,200);self.assertIn('Solucionario',r.json['respuesta'])
    def test_10_herramienta_no_permitida(self):self.error(Secuencia(llamada('borrar_registros')),'herramienta_invalida')
    def test_11_argumentos_no_permitidos(self):self.error(Secuencia(llamada(args={'sql':'DELETE FROM interacciones'})),'herramienta_invalida')
    def test_12_rechaza_cita_inexistente(self):self.error(Secuencia(llamada(),{'content':'Hallazgo [ID 999]'}),'cita_invalida')
    def test_13_rechaza_respuesta_sin_herramienta(self):self.error(Secuencia({'content':'Hay cien consultas.'}),'sin_herramientas')
    def test_14_rechaza_respuesta_sin_citas(self):self.error(Secuencia(llamada(),{'content':'Informe sin referencias.'}),'sin_citas')
    def test_15_limite_de_pasos(self):self.error(Secuencia(*[llamada() for _ in range(4)]),'limite_pasos')
    def test_16_historial_no_modificado(self):
        before=self.path.read_bytes();self.good_model();self.post();self.assertEqual(before,self.path.read_bytes())
    def test_17_token_exigido(self):
        os.environ['YACHAYBOT_TOKEN']='token-prueba';self.assertEqual(self.post().status_code,401)
        self.good_model();r=self.c.post('/api/agente',json=self.payload,headers={'X-Yachay-Token':'token-prueba'});self.assertEqual(r.status_code,200)
    def test_18_bitacora_sin_textos(self):
        self.good_model();r=self.post();self.assertTrue(r.json['bitacora_guardada'])
        log=Path(self.app.config['AGENTE_LOG']).read_text();self.assertNotIn('¿Qué es una fracción?',log)
        self.assertNotIn('Resume las consultas',log);self.assertIn('solicitud_sha256',log)
    def test_19_sql_injection_no_cambia_datos(self):
        self.app.config['AGENTE_MODELO']=Secuencia(llamada());self.payload['tema']="'; DROP TABLE interacciones; --"
        self.assertEqual(self.post().json['resumen']['total'],0)
        with sqlite3.connect(self.path) as c:self.assertEqual(c.execute('select count(*) from interacciones').fetchone()[0],4)
    def test_20_contrato_http_ollama(self):
        class Resp:
            def raise_for_status(self):pass
            def json(self):return {'message':{'role':'assistant','content':'prueba'}}
        with patch('agente_docente.requests.post',return_value=Resp()) as post:
            model=ModeloHTTP(provider='ollama',model='modelo-prueba');self.assertEqual(model([])['content'],'prueba')
            self.assertTrue(post.call_args.args[0].endswith('/api/chat'));self.assertFalse(post.call_args.kwargs['json']['stream'])
            self.assertEqual(post.call_args.kwargs['json']['tools'][0]['function']['name'],'resumir_historial')
    def test_21_contrato_http_groq(self):
        class Resp:
            def raise_for_status(self):pass
            def json(self):return {'choices':[{'message':{'role':'assistant','content':'prueba'}}]}
        with patch('agente_docente.requests.post',return_value=Resp()) as post:
            ModeloHTTP(provider='groq',key='sintetica')([])
            self.assertTrue(post.call_args.args[0].endswith('/chat/completions'))
            self.assertEqual(post.call_args.kwargs['headers']['Authorization'],'Bearer sintetica')
    def test_22_timeout(self):
        self.app.config['AGENTE_MODELO']=ModeloHTTP(provider='ollama')
        with patch('agente_docente.requests.post',side_effect=requests.Timeout):self.error(self.app.config['AGENTE_MODELO'],'tiempo_agotado',504)
    def test_23_modelo_no_disponible(self):
        self.app.config['AGENTE_MODELO']=ModeloHTTP(provider='ollama')
        with patch('agente_docente.requests.post',side_effect=requests.ConnectionError):self.error(self.app.config['AGENTE_MODELO'],'modelo_no_disponible',503)
    def test_24_muestra_limitada_con_conteos_completos(self):
        with sqlite3.connect(self.path) as c:c.executemany('insert into interacciones values(?,?,?,?)',[(i,'2026-08-22T12:00:00','Suma','Matemática') for i in range(5,65)])
        self.good_model('Resumen de consultas [ID 64].');r=self.post();self.assertEqual(r.json['resumen']['total'],64);self.assertEqual(len(r.json['resumen']['muestra']),30)
    def test_25_datos_estructuralmente_invalidos(self):
        for payload in [None,[],{'solicitud':5},{**self.payload,'todo_historial':'si'},{**self.payload,'tarea':'borrar'}]:
            r=self.c.post('/api/agente',data=json.dumps(payload),content_type='application/json');self.assertEqual(r.status_code,400)
    def test_26_esquema_sqlite_ausente(self):
        self.path.unlink();sqlite3.connect(self.path).close();self.good_model();self.assertEqual(self.post().status_code,503)
    def test_27_resultado_tool_groq(self):
        self.app.config['AGENTE_PROVIDER']='groq';model=self.good_model();self.post()
        self.assertTrue(any(m.get('tool_call_id')=='call_1' for m in model.inputs[1]))

if __name__=='__main__':unittest.main(verbosity=2)
