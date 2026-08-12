import { Component, computed, effect, inject, signal } from '@angular/core';
import { Botao } from '../../../componentes/botao/botao';
import { CartaoKpi } from '../../../componentes/cartao-kpi/cartao-kpi';
import { Dialog } from '../../../componentes/dialog/dialog';
import { ModuloHeader } from '../../../componentes/modulo-header/modulo-header';
import { SeletorArquivoCurriculo } from '../../../componentes/seletor-arquivo-curriculo/seletor-arquivo-curriculo';
import { OpcaoSelectBusca, SelectBusca } from '../../../componentes/select-busca/select-busca';
import {
  AnaliseCurriculo,
  Candidato,
  CORES_FIT,
  ROTULOS_FIT,
  ROTULOS_STATUS,
  StatusCandidato,
  nivelFit,
} from '../../../servicos/analise-curriculo';

/** MÓDULO RH — TELA "DNA AGRO" (2026-08)
 *
 * Vagas e candidatos agora são reais (Postgres, via `AnaliseCurriculo`) —
 * só a pontuação em si continua mock (ver docstring de
 * `tools/rh/candidatos.py` no backend). Esta tela só lê e exibe: nada de
 * dado sobrevive a uma navegação pra fora daqui, então candidatos/análises
 * em andamento moram no serviço (mesmo motivo de `Auditoria` existir pro
 * sino/painel de auditoria).
 *
 * As métricas de candidato (KPIs "Currículos Analisados"/"Alto Fit") são
 * escopadas pela vaga selecionada — não existe um "total geral" carregado
 * de uma vez, cada `carregarCandidatos(vagaId)` busca só os candidatos
 * daquela vaga.
 *
 * Fluxo pedido pelo RH: escolher a vaga, subir o currículo (botão "Analisar
 * Currículo" → dialog), a análise roda em segundo plano
 * (`AnaliseCurriculo.iniciarAnalise`, POST que o componente não espera) e o
 * dialog fecha na hora. Quando termina, um toast global
 * (`NotificacaoAnaliseCurriculo`, montado no layout) avisa em qualquer tela
 * do sistema; "Ver resultado" volta pra cá e abre o candidato certo
 * (`candidatoParaAbrir`, observado no `effect()` do construtor).
 */

@Component({
  selector: 'app-rh',
  imports: [ModuloHeader, SelectBusca, Botao, CartaoKpi, Dialog, SeletorArquivoCurriculo],
  templateUrl: './rh.html',
  styleUrl: './rh.scss',
})
export class Rh {
  private readonly analiseCurriculo = inject(AnaliseCurriculo);

  protected readonly vagas = computed<OpcaoSelectBusca[]>(() =>
    this.analiseCurriculo
      .vagas()
      .filter((vaga) => vaga.ativa)
      .map((vaga) => ({ valor: String(vaga.id), rotulo: `${vaga.titulo} — ${vaga.localizacao}` })),
  );
  protected readonly vagaSelecionada = signal<string | null>(null);

  protected readonly jaCarregou = signal(false);
  protected readonly candidatoAberto = signal<Candidato | null>(null);

  protected readonly dialogAnaliseAberto = signal(false);
  protected readonly vagaAnalise = signal<string | null>(null);
  protected readonly arquivoAnalise = signal<File | null>(null);

  protected readonly podeCarregar = computed(() => !!this.vagaSelecionada());
  protected readonly podeIniciarAnalise = computed(() => !!this.vagaAnalise() && !!this.arquivoAnalise());

  protected readonly candidatosDaVaga = computed(() =>
    [...this.analiseCurriculo.candidatos()].sort((a, b) => b.score - a.score),
  );

  protected readonly vagasCriticasAbertas = computed(
    () => this.analiseCurriculo.vagas().filter((vaga) => vaga.ativa).length,
  );
  protected readonly curriculosAnalisados = computed(() => this.candidatosDaVaga().length);
  protected readonly tempoMedioPreenchimento = computed(() => {
    const vagas = this.analiseCurriculo.vagas().filter((vaga) => vaga.ativa);
    if (!vagas.length) {
      return 0;
    }
    const totalDias = vagas.reduce((soma, vaga) => soma + this.diasDesde(vaga.criado_em), 0);
    return Math.round(totalDias / vagas.length);
  });
  protected readonly percentualAltoFit = computed(() => {
    const candidatos = this.candidatosDaVaga();
    if (!candidatos.length) {
      return 0;
    }
    const altoFit = candidatos.filter((candidato) => nivelFit(candidato.score) === 'alto').length;
    return (altoFit / candidatos.length) * 100;
  });

  constructor() {
    effect(() => {
      const candidato = this.analiseCurriculo.candidatoParaAbrir();
      if (!candidato) {
        return;
      }
      this.vagaSelecionada.set(String(candidato.vaga_id));
      this.jaCarregou.set(true);
      this.candidatoAberto.set(candidato);
      this.analiseCurriculo.limparCandidatoParaAbrir();
    });
  }

  protected abrirDetalhe(candidato: Candidato): void {
    this.candidatoAberto.set(candidato);
  }

  protected abrirDialogAnalise(): void {
    this.vagaAnalise.set(this.vagaSelecionada());
    this.arquivoAnalise.set(null);
    this.dialogAnaliseAberto.set(true);
  }

  protected atualizarStatus(candidato: Candidato, status: StatusCandidato): void {
    if (candidato.id === null) {
      return;
    }
    this.analiseCurriculo.atualizarStatusCandidato(candidato.id, status);
    this.candidatoAberto.update((atual) => (atual && atual.id === candidato.id ? { ...atual, status } : atual));
  }

  protected carregarCandidatos(): void {
    const vagaId = this.vagaSelecionada();
    if (!vagaId) {
      return;
    }
    this.jaCarregou.set(true);
    this.analiseCurriculo.carregarCandidatos(Number(vagaId));
  }

  protected definirArquivoAnalise(arquivo: File | null): void {
    this.arquivoAnalise.set(arquivo);
  }

  protected criteriosCandidato(candidato: Candidato) {
    return candidato.criterios;
  }

  private diasDesde(dataIso: string): number {
    const diffMs = Date.now() - new Date(dataIso).getTime();
    return Math.max(0, Math.round(diffMs / 86_400_000));
  }

  protected estiloScore(score: number): Record<string, string> {
    const cor = CORES_FIT[nivelFit(score)];
    return { background: `conic-gradient(${cor} ${score * 3.6}deg, var(--color-border) 0deg)` };
  }

  protected fecharDetalhe(): void {
    this.candidatoAberto.set(null);
  }

  protected fecharDialogAnalise(): void {
    this.dialogAnaliseAberto.set(false);
  }

  protected iniciarAnalise(): void {
    const vagaId = this.vagaAnalise();
    const arquivo = this.arquivoAnalise();
    if (!vagaId || !arquivo) {
      return;
    }
    this.analiseCurriculo.iniciarAnalise(arquivo, Number(vagaId));
    this.dialogAnaliseAberto.set(false);
  }

  protected nivelFit(score: number) {
    return nivelFit(score);
  }

  protected rotuloAnalisadoHa(criadoEm: string): string {
    const dias = this.diasDesde(criadoEm);
    return dias === 0 ? 'hoje' : dias === 1 ? 'há 1 dia' : `há ${dias} dias`;
  }

  protected rotuloFit(score: number): string {
    return ROTULOS_FIT[nivelFit(score)];
  }

  protected rotuloStatus(status: StatusCandidato): string {
    return ROTULOS_STATUS[status];
  }

  protected temVagaSugeridaDiferente(candidato: Candidato): boolean {
    return candidato.vaga_sugerida_id !== candidato.vaga_id;
  }

  protected vagaSugeridaTitulo(candidato: Candidato): string {
    return this.analiseCurriculo.tituloVaga(candidato.vaga_sugerida_id);
  }
}
