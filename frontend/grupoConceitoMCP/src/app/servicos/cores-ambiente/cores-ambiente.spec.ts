import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Sessao } from '../sessao/sessao';
import { CoresAmbiente, TOKENS_AMBIENTE } from './cores-ambiente';

function sessaoFalso(token: string | null) {
  return { token: signal(token) };
}

function criar(token: string | null = 'token-teste') {
  TestBed.configureTestingModule({
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      { provide: Sessao, useValue: sessaoFalso(token) },
    ],
  });
  const servico = TestBed.inject(CoresAmbiente);
  TestBed.tick();
  const http = TestBed.inject(HttpTestingController);
  return { servico, http };
}

describe('CoresAmbiente', () => {
  afterEach(() => {
    // Cada teste aplica cor direto no <html> de verdade (é o ponto da
    // classe) — sem limpar, um teste vaza estilo pro próximo.
    for (const item of TOKENS_AMBIENTE) {
      document.documentElement.style.removeProperty(item.token);
    }
  });

  it('com token, carrega as cores salvas do backend', () => {
    const { http } = criar();

    const requisicao = http.expectOne((req) => req.url.endsWith('/api/auth/cores-ambiente'));
    expect(requisicao.request.method).toBe('GET');
    requisicao.flush([{ token: '--color-primary', cor: '#123456' }]);
    TestBed.tick();

    expect(document.documentElement.style.getPropertyValue('--color-primary')).toBe('#123456');
  });

  it('sem token, não chama o backend e não aplica nada', () => {
    const { http } = criar(null);

    http.expectNone((req) => req.url.endsWith('/api/auth/cores-ambiente'));
    expect(document.documentElement.style.getPropertyValue('--color-primary')).toBe('');
  });

  it('token sem cor personalizada não aparece no documento (usa o padrão do CSS)', () => {
    const { http } = criar();

    http.expectOne((req) => req.url.endsWith('/api/auth/cores-ambiente')).flush([]);
    TestBed.tick();

    for (const item of TOKENS_AMBIENTE) {
      expect(document.documentElement.style.getPropertyValue(item.token)).toBe('');
    }
  });

  it('listaParaExibir mostra a cor padrão pra token sem personalização', () => {
    const { servico, http } = criar();
    http.expectOne((req) => req.url.endsWith('/api/auth/cores-ambiente')).flush([]);

    const item = servico.listaParaExibir().find((i) => i.token === '--color-primary');

    expect(item?.cor).toBe('#1b4332');
    expect(item?.personalizada).toBe(false);
  });

  it('aplicarCorLocal atualiza a lista e aplica no documento na hora, sem esperar o backend', () => {
    const { servico, http } = criar();
    http.expectOne((req) => req.url.endsWith('/api/auth/cores-ambiente')).flush([]);
    TestBed.tick();

    servico.aplicarCorLocal('--color-accent', '#abcdef');
    TestBed.tick();

    const item = servico.listaParaExibir().find((i) => i.token === '--color-accent');
    expect(item?.cor).toBe('#abcdef');
    expect(item?.personalizada).toBe(true);
    expect(document.documentElement.style.getPropertyValue('--color-accent')).toBe('#abcdef');
  });

  it('removerCorLocal volta a cor pro padrão e some do documento', () => {
    const { servico, http } = criar();
    http.expectOne((req) => req.url.endsWith('/api/auth/cores-ambiente')).flush([
      { token: '--color-primary', cor: '#123456' },
    ]);
    TestBed.tick();

    servico.removerCorLocal('--color-primary');
    TestBed.tick();

    const item = servico.listaParaExibir().find((i) => i.token === '--color-primary');
    expect(item?.cor).toBe('#1b4332');
    expect(item?.personalizada).toBe(false);
    expect(document.documentElement.style.getPropertyValue('--color-primary')).toBe('');
  });

  it('definirCor chama a rota certa', () => {
    const { servico, http } = criar();
    http.expectOne((req) => req.url.endsWith('/api/auth/cores-ambiente')).flush([]);

    servico.definirCor('--color-primary', '#000000').subscribe();

    const requisicao = http.expectOne(
      (req) => req.url.endsWith('/api/auth/cores-ambiente/--color-primary') && req.method === 'PUT',
    );
    expect(requisicao.request.body).toEqual({ cor: '#000000' });
    requisicao.flush({ token: '--color-primary', cor: '#000000' });
  });

  it('redefinirCor chama a rota certa', () => {
    const { servico, http } = criar();
    http.expectOne((req) => req.url.endsWith('/api/auth/cores-ambiente')).flush([]);

    servico.redefinirCor('--color-primary').subscribe();

    const requisicao = http.expectOne(
      (req) => req.url.endsWith('/api/auth/cores-ambiente/--color-primary') && req.method === 'DELETE',
    );
    requisicao.flush({});
  });
});
