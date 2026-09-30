import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { DadosSessao, Sessao } from './sessao';

function dadosSessao(overrides: Partial<DadosSessao> = {}): DadosSessao {
  return {
    token: 'token-teste',
    usuario: 'usuario.teste',
    nome: 'Usuário Teste',
    foto: null,
    papeis: [],
    administrador: false,
    modulos: [],
    ...overrides,
  };
}

describe('Sessao', () => {
  let servico: Sessao;

  beforeEach(() => {
    localStorage.removeItem('sessao:usuario');
    TestBed.configureTestingModule({ providers: [provideRouter([])] });
    servico = TestBed.inject(Sessao);
  });

  afterEach(() => localStorage.removeItem('sessao:usuario'));

  describe('ehAdminDoModulo', () => {
    it('deveria ser true pro admin do próprio módulo', () => {
      servico.entrar(dadosSessao({ papeis: ['financeiro_admin'], administrador: true, modulos: ['financeiro'] }));

      expect(servico.ehAdminDoModulo('financeiro')).toBe(true);
    });

    it('deveria ser false pro admin de outro módulo', () => {
      servico.entrar(dadosSessao({ papeis: ['financeiro_admin'], administrador: true, modulos: ['financeiro'] }));

      expect(servico.ehAdminDoModulo('ti')).toBe(false);
    });

    it('deveria ser false pra usuário comum do módulo (sem ser administrador)', () => {
      servico.entrar(dadosSessao({ papeis: ['financeiro'], administrador: false, modulos: ['financeiro'] }));

      expect(servico.ehAdminDoModulo('financeiro')).toBe(false);
    });

    it('deveria ser false sem sessão nenhuma', () => {
      expect(servico.ehAdminDoModulo('financeiro')).toBe(false);
    });
  });
});
