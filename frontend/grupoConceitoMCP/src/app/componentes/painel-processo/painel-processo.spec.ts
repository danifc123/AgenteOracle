import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { EtapaProcesso, PainelProcesso } from './painel-processo';

describe('PainelProcesso', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [PainelProcesso] }).compileComponents();
  });

  const ETAPAS: EtapaProcesso[] = [
    { id: 'um', rotulo: 'Primeira etapa', status: 'concluido', processados: 3 },
    { id: 'dois', rotulo: 'Segunda etapa', status: 'rodando', processados: null },
    { id: 'tres', rotulo: 'Terceira etapa', status: 'pendente', processados: null },
  ];

  it('fechado não renderiza nada', () => {
    const fixture = TestBed.createComponent(PainelProcesso);
    fixture.componentRef.setInput('aberto', false);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.painel')).toBeNull();
  });

  it('aberto mostra o título e cada etapa com o status certo', () => {
    const fixture = TestBed.createComponent(PainelProcesso);
    fixture.componentRef.setInput('aberto', true);
    fixture.componentRef.setInput('titulo', 'Poller do GLPI');
    fixture.componentRef.setInput('etapas', ETAPAS);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('h2')?.textContent).toBe('Poller do GLPI');

    const marcadores = compiled.querySelectorAll('.etapa-marcador');
    expect(marcadores[0].classList.contains('etapa-marcador--concluida')).toBe(true);
    expect(marcadores[1].classList.contains('etapa-marcador--rodando')).toBe(true);
    expect(marcadores[2].classList.contains('etapa-marcador--concluida')).toBe(false);
    expect(marcadores[2].classList.contains('etapa-marcador--rodando')).toBe(false);

    expect(compiled.querySelector('.progresso-texto')?.textContent).toContain('1 de 3');
  });

  it('mostra a mensagem de erro quando a última rodada falhou', () => {
    const fixture = TestBed.createComponent(PainelProcesso);
    fixture.componentRef.setInput('aberto', true);
    fixture.componentRef.setInput('erro', 'GLPI fora do ar');
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.aviso-erro')?.textContent).toContain('GLPI fora do ar');
  });

  it('conta regressiva até a próxima rodada e atualiza sozinha a cada segundo', () => {
    vi.useFakeTimers();
    const agora = new Date('2026-10-01T12:00:00Z');
    vi.setSystemTime(agora);

    const fixture = TestBed.createComponent(PainelProcesso);
    fixture.componentRef.setInput('aberto', true);
    fixture.componentRef.setInput('proximaRodadaEm', new Date('2026-10-01T12:05:00Z').toISOString());
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.rodape-contagem')?.textContent).toBe('00:05:00');

    vi.advanceTimersByTime(60_000);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.rodape-contagem')?.textContent).toBe('00:04:00');

    vi.useRealTimers();
  });

  it('fechar e reabrir não mostra um número travado do fechamento anterior', () => {
    // Regressão: o relógio só reagia ao `setInterval` (1 tick/segundo) —
    // fechado o painel, o `setInterval` para, mas o signal "agora" ficava
    // parado no último valor. Reabrir mostrava esse valor congelado por
    // até 1s, até o primeiro tick novo corrigir (achado do usuário
    // testando ao vivo, 2026-10-01).
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-01T12:00:00Z'));

    const fixture = TestBed.createComponent(PainelProcesso);
    fixture.componentRef.setInput('aberto', true);
    fixture.componentRef.setInput('proximaRodadaEm', new Date('2026-10-01T12:05:00Z').toISOString());
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.rodape-contagem')?.textContent).toBe('00:05:00');

    fixture.componentRef.setInput('aberto', false);
    fixture.detectChanges();

    // Passa 2 minutos com o painel FECHADO — nenhum tick roda nesse meio
    // tempo, só o relógio do sistema avança de verdade.
    vi.setSystemTime(new Date('2026-10-01T12:02:00Z'));

    fixture.componentRef.setInput('aberto', true);
    fixture.detectChanges(); // sem avançar o fake timer — testa o valor do 1º render

    expect(fixture.nativeElement.querySelector('.rodape-contagem')?.textContent).toBe('00:03:00');

    vi.useRealTimers();
  });

  it('enquanto uma etapa está rodando, mostra "Rodando agora" em vez da contagem travada', () => {
    // Regressão: `proximaRodadaEm` só é recalculado pelo backend quando a
    // rodada ATUAL termina — enquanto ela roda, o horário ainda é o da
    // rodada anterior, já no passado, e a contagem regressiva travava em
    // "00:00:00" (achado do usuário testando ao vivo, 2026-10-01).
    const fixture = TestBed.createComponent(PainelProcesso);
    fixture.componentRef.setInput('aberto', true);
    fixture.componentRef.setInput('etapas', [
      { id: 'um', rotulo: 'Primeira etapa', status: 'rodando', processados: null },
      { id: 'dois', rotulo: 'Segunda etapa', status: 'pendente', processados: null },
    ]);
    fixture.componentRef.setInput('proximaRodadaEm', new Date(Date.now() - 1000).toISOString());
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.rodape-rodando')?.textContent).toContain('Rodando agora');
    expect(compiled.querySelector('.rodape-contagem')).toBeNull();
    expect(compiled.querySelector('.rodape-horario')).toBeNull();
  });

  it('Esc fecha o painel', () => {
    const fixture = TestBed.createComponent(PainelProcesso);
    fixture.componentRef.setInput('aberto', true);
    fixture.detectChanges();

    const fechouSpy = vi.fn();
    fixture.componentInstance.fechar.subscribe(fechouSpy);

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));

    expect(fechouSpy).toHaveBeenCalled();
  });

  it('clicar no botão fechar emite o evento fechar', () => {
    const fixture = TestBed.createComponent(PainelProcesso);
    fixture.componentRef.setInput('aberto', true);
    fixture.detectChanges();

    const fechouSpy = vi.fn();
    fixture.componentInstance.fechar.subscribe(fechouSpy);

    (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('.fechar')?.click();

    expect(fechouSpy).toHaveBeenCalled();
  });

  it('log detalhado começa fechado, e o chevron mostra/esconde as linhas', () => {
    const fixture = TestBed.createComponent(PainelProcesso);
    fixture.componentRef.setInput('aberto', true);
    fixture.componentRef.setInput('logs', ['09:58:02 Rodada iniciada', '09:58:05 Chamado #1 liberado pra Fulano']);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.log-conteudo')).toBeNull();

    compiled.querySelector<HTMLButtonElement>('.log-toggle')?.click();
    fixture.detectChanges();

    const linhas = Array.from(compiled.querySelectorAll('.log-linha')).map((linha) => linha.textContent);
    expect(linhas).toEqual(['09:58:02 Rodada iniciada', '09:58:05 Chamado #1 liberado pra Fulano']);

    compiled.querySelector<HTMLButtonElement>('.log-toggle')?.click();
    fixture.detectChanges();

    expect(compiled.querySelector('.log-conteudo')).toBeNull();
  });

  it('log detalhado vazio mostra um aviso em vez de uma caixa em branco', () => {
    const fixture = TestBed.createComponent(PainelProcesso);
    fixture.componentRef.setInput('aberto', true);
    fixture.componentRef.setInput('logs', []);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    compiled.querySelector<HTMLButtonElement>('.log-toggle')?.click();
    fixture.detectChanges();

    expect(compiled.querySelector('.log-linha--vazio')).toBeTruthy();
  });
});
