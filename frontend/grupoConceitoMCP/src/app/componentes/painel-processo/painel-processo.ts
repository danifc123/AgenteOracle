import {
  Component,
  ElementRef,
  HostListener,
  ViewChild,
  computed,
  effect,
  input,
  output,
  signal,
} from '@angular/core';
import { DatePipe } from '@angular/common';

export type StatusEtapaProcesso = 'pendente' | 'rodando' | 'concluido' | 'erro';

export interface EtapaProcesso {
  id: string;
  rotulo: string;
  status: StatusEtapaProcesso;
  processados: number | null;
}

/** Painel lateral genérico pra acompanhar um processo em etapas — nasce
 * aqui conectado ao poller do GLPI (`pages/modulos/ti/chamados`), mas não
 * sabe nada sobre GLPI: qualquer tela com outro processo em etapas pode
 * reusar, só passando os inputs certos. Mesma API de `Dialog`
 * (`aberto`/`titulo`/`fechar`, fecha com Esc), CSS diferente (desliza da
 * direita em vez de modal centralizado). */
@Component({
  selector: 'app-painel-processo',
  imports: [DatePipe],
  templateUrl: './painel-processo.html',
  styleUrl: './painel-processo.scss',
})
export class PainelProcesso {
  aberto = input(false);
  titulo = input('');
  etapas = input<EtapaProcesso[]>([]);
  ultimaRodadaEm = input<string | null>(null);
  proximaRodadaEm = input<string | null>(null);
  erro = input<string | null>(null);
  // Linhas do log ao vivo (`PollerTi.logs`) — cada rótulo de etapa já
  // conta "o quê"; isso aqui é o "quando/pra quem", chamado a chamado,
  // à medida que o backend processa (ver `servicos/poller-ti/poller-ti.ts`).
  logs = input<string[]>([]);

  fechar = output<void>();

  protected readonly logsExpandidos = signal(false);

  @ViewChild('logContainer') private readonly logContainerRef?: ElementRef<HTMLDivElement>;

  protected alternarLogs(): void {
    this.logsExpandidos.update((atual) => !atual);
  }

  @HostListener('document:keydown.escape')
  aoPressionarEsc(): void {
    if (this.aberto()) {
      this.fechar.emit();
    }
  }

  private readonly agora = signal(Date.now());

  constructor() {
    // Só faz o relógio da contagem regressiva correr enquanto o painel
    // está de fato aberto — sem isso, o `setInterval` ficaria vivo pro
    // resto da sessão, mesmo com o painel fechado (o componente continua
    // instanciado, só o conteúdo que some via `@if` no template).
    effect((onCleanup) => {
      if (!this.aberto()) {
        return;
      }
      // Atualiza na hora de abrir — sem isso, `agora` ficava com o valor
      // congelado de quando o painel foi fechado da última vez, e a
      // contagem regressiva mostrava um número velho por até 1s até o
      // primeiro tick do `setInterval` corrigir (achado do usuário
      // testando ao vivo, 2026-10-01).
      this.agora.set(Date.now());
      const intervalo = setInterval(() => this.agora.set(Date.now()), 1000);
      onCleanup(() => clearInterval(intervalo));
    });

    // Rola pro fim a cada linha nova — só importa enquanto a seção de log
    // está expandida (fechada, não tem elemento pra rolar).
    effect(() => {
      this.logs();
      if (!this.logsExpandidos()) {
        return;
      }
      const elemento = this.logContainerRef?.nativeElement;
      if (elemento) {
        elemento.scrollTop = elemento.scrollHeight;
      }
    });
  }

  protected readonly etapasConcluidas = computed(
    () => this.etapas().filter((etapa) => etapa.status === 'concluido').length,
  );

  // Enquanto alguma etapa está rodando, `proximaRodadaEm` ainda é o
  // horário da rodada ANTERIOR (o backend só recalcula depois que a
  // rodada atual termina) — mostrar a contagem regressiva nesse momento
  // trava em "00:00:00" e parece quebrado. "Rodando agora" é a leitura
  // honesta do que está acontecendo nesse instante.
  protected readonly rodandoAgora = computed(() => this.etapas().some((etapa) => etapa.status === 'rodando'));

  protected readonly progresso = computed(() => {
    const total = this.etapas().length;
    return total === 0 ? 0 : (this.etapasConcluidas() / total) * 100;
  });

  protected readonly contagemRegressiva = computed(() => {
    const proxima = this.proximaRodadaEm();
    if (!proxima) {
      return null;
    }
    const restanteMs = new Date(proxima).getTime() - this.agora();
    const totalSegundos = Math.max(0, Math.floor(restanteMs / 1000));
    const horas = Math.floor(totalSegundos / 3600);
    const minutos = Math.floor((totalSegundos % 3600) / 60);
    const segundos = totalSegundos % 60;
    return [horas, minutos, segundos].map((parte) => String(parte).padStart(2, '0')).join(':');
  });
}
