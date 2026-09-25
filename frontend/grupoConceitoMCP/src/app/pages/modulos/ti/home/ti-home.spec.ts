import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { Sessao } from '../../../../servicos/sessao/sessao';
import { ChamadosIaResposta, UsoIa } from '../../../../servicos/uso-ia/uso-ia';
import { TiHome } from './ti-home';

function sessaoFalso(ehDesenvolvedor = false) {
  return { ehDesenvolvedor: () => ehDesenvolvedor };
}

function usoIaFalso() {
  return {
    tokensHojePorDominio: signal<Record<string, number>>({ ti: 300, rh: 200 }),
    chamadosIa: signal<ChamadosIaResposta | null>({
      total_chamados: 10,
      avaliados_insuficientes: 2,
      com_fallback_embedding: 1,
      duracao_media_ms: 500,
    }),
    carregar: vi.fn(),
  };
}

function criar(
  chamados: { status: string }[] = [],
  sessao = sessaoFalso(),
  usoIa = usoIaFalso(),
) {
  TestBed.configureTestingModule({
    imports: [TiHome],
    providers: [
      provideRouter([]),
      provideHttpClient(),
      provideHttpClientTesting(),
      { provide: Sessao, useValue: sessao },
      { provide: UsoIa, useValue: usoIa },
    ],
  });
  const fixture = TestBed.createComponent(TiHome);
  const http = TestBed.inject(HttpTestingController);
  http.expectOne((req) => req.url.endsWith('/api/ti/chamados')).flush(chamados);
  fixture.detectChanges();

  const el: HTMLElement = fixture.nativeElement;
  return {
    fixture,
    usoIa,
    http,
    texto: () => el.textContent ?? '',
  };
}

describe('TiHome', () => {
  afterEach(() => {
    TestBed.inject(HttpTestingController).verify();
  });

  it('sem chamado em aberto, mostra a mensagem de "tudo em dia"', () => {
    const { texto } = criar([]);

    expect(texto()).toContain('Nenhum chamado em aberto agora');
  });

  it('mostra o total de chamados em aberto e o gráfico por status', () => {
    const { texto, fixture } = criar([
      { status: 'novo' },
      { status: 'novo' },
      { status: 'aguardando_usuario' },
    ]);

    expect(texto()).toContain('Em aberto agora');
    expect(texto()).toContain('3');
    expect(fixture.nativeElement.querySelector('app-grafico-rosca')).not.toBeNull();
  });

  it('usuário de TI comum não vê a seção de consumo de IA, nem dispara a chamada', () => {
    const usoIa = usoIaFalso();
    const { texto } = criar([], sessaoFalso(false), usoIa);

    expect(texto()).not.toContain('Consumo de IA');
    expect(usoIa.carregar).not.toHaveBeenCalled();
  });

  it('desenvolvedor vê a seção de consumo de IA com os números do uso de IA', () => {
    const usoIa = usoIaFalso();
    const { texto } = criar([], sessaoFalso(true), usoIa);

    expect(usoIa.carregar).toHaveBeenCalled();
    expect(texto()).toContain('Consumo de IA');
    expect(texto()).toContain('Só você vê isso');
    expect(texto()).toContain('500'); // tokens hoje = 300 (ti) + 200 (rh)
    expect(texto()).toContain('Ver detalhes em IA');
  });

  it('mostra quantos chamados ficaram sem correção automática de categoria por falta de embedding', () => {
    // Dado que já existia no backend/interface (`ChamadosIaResposta.
    // com_fallback_embedding`) mas nunca aparecia em lugar nenhum da tela
    // — só um toast passageiro na Auditoria de Chamados, e só quando
    // alguém clicava "Verificar" manualmente.
    const { texto } = criar([], sessaoFalso(true));

    expect(texto()).toContain('Categoria não corrigida automaticamente (30d)');
    expect(texto()).toContain('1'); // com_fallback_embedding do fake
  });

  it('atalhos de sempre continuam presentes (Segurança, Auditoria de Chamados, Central de suporte)', () => {
    const { texto } = criar([]);

    expect(texto()).toContain('Segurança de TI');
    expect(texto()).toContain('Auditoria de Chamados');
    expect(texto()).toContain('Central de suporte');
  });
});
