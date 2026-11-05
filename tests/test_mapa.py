import sys, unittest, math, os

os.environ['DATABASE_URL']='sqlite:///:memory:'
os.environ['DESATIVAR_VERIFICADOR']='1'
import mapa_rotograma as M
import faixa_geografica as F
from types import SimpleNamespace as N

class Mapa(unittest.TestCase):
    def test_limite_capsula(self):
        a,b=[-46.29,-24.02],[-49.26,-16.64]
        g=M.geometria(dict(ativa=True,erro=None,origem={'ponto':a},destino={'ponto':b},raio_km=40))
        for p in g['anel']:
            self.assertAlmostEqual(F.distancia_segmento(p,a,b),40,places=5)
        self.assertEqual(g['anel'][0],g['anel'][-1])
    def test_mesmo_ponto(self):
        a=[0,0];g=M.geometria(dict(ativa=True,erro=None,origem={'ponto':a},destino={'ponto':a},raio_km=30))
        for p in g['anel']:self.assertAlmostEqual(F.distancia_segmento(p,a,a),30,places=6)
    def test_marcadores_ausentes_e_precisao(self):
        import municipios
        r=N(origem='Santos',origem_uf='SP',origem_latitude=None,origem_longitude=None,destino='X',destino_uf='SP',destino_latitude=None,destino_longitude=None)
        c=N(nome='<teste>',cidade='',estado='',latitude=-22,longitude=-47)
        p=N(nome='Posto',cidade='Araras',estado='SP')
        d=M.dados(r,[N(cerca=c)],[N(posto=p)],municipios.carregar(),{'ativa':False})
        self.assertEqual(len(d['marcadores']),3)
        self.assertEqual(d['ausentes'],['Destino · X'])
        self.assertEqual(d['marcadores'][1]['precisao'],'Coordenadas informadas')
    def test_template(self):
        import app as S
        with S.app.app_context():S.app.jinja_env.get_template('detalhe_rotograma.html')

if __name__ == '__main__': unittest.main()
