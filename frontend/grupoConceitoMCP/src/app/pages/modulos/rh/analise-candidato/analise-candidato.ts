import { Component, computed, inject, signal } from '@angular/core';
import { Botao } from '../../../../componentes/botao/botao';
import { CartaoKpi } from '../../../../componentes/cartao-kpi/cartao-kpi';
import { DetalheCandidato } from '../../../../componentes/detalhe-candidato/detalhe-candidato';
import { Dialog } from '../../../../componentes/dialog/dialog';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { SeletorArquivoCurriculo } from '../../../../componentes/seletor-arquivo-curriculo/seletor-arquivo-curriculo';
import {
  AnaliseCurriculo,
  Candidato,
  ROTULOS_STATUS,
  StatusCandidato,
} from '../../../../servicos/analise-curriculo';

const LIMITE_RESUMO_TRUNCADO = 140;

/** MÓDULO RH — TELA "ANÁLISE DE CANDIDATO" (2026-08)
 *
 * Substitui a tela antiga "DNA Agro" — não existe mais vaga cadastrada nem
 * score fixo contra dimensões genéricas (ver docstring de
 * `servicos/analise-curriculo.ts`). O RH sobe um ou mais currículos de uma
 * vez (`SeletorArquivoCurriculo` em modo múltiplo); cada arquivo dispara
 * sua própria análise em segundo plano (`iniciarAnalises` chama
 * `AnaliseCurriculo.iniciarAnalise` uma vez por arquivo), o dialog fecha
 * na hora, e cada currículo avisa via toast quando termina, independente
 * dos outros do mesmo lote. Todo candidato analisado com sucesso entra no
 * pool (tabela principal desta tela) — a compatibilidade com uma vaga
 * específica só é calculada depois, sob demanda, na tela "Selecionar
 * Candidato".
 */
@Component({
  selector: 'app-analise-candidato',
  imports: [Botao, CartaoKpi, DetalheCandidato, Dialog, ModuloHeader, SeletorArquivoCurriculo],
  templateUrl: './analise-candidato.html',
  styleUrl: './analise-candidato.scss',
})
export class AnaliseCandidato {
  protected readonly analiseCurriculo = inject(AnaliseCurriculo);

  protected readonly dialogAnaliseAberto = signal(false);
  protected readonly arquivosSelecionados = signal<File[]>([]);
  protected readonly candidatoAberto = signal<Candidato | null>(null);

  protected readonly candidatosAtivos = computed(() =>
    this.analiseCurriculo.candidatos().filter((candidato) => candidato.status === 'ativo'),
  );
  protected readonly totalAtivos = computed(() => this.candidatosAtivos().length);

  constructor() {
    this.analiseCurriculo.carregarCandidatos('ativo');
  }

  protected abrirDetalhe(candidato: Candidato): void {
    this.candidatoAberto.set(candidato);
  }

  protected abrirDialogAnalise(): void {
    this.arquivosSelecionados.set([]);
    this.dialogAnaliseAberto.set(true);
  }

  protected atualizarStatus(candidato: Candidato, status: StatusCandidato): void {
    this.analiseCurriculo.atualizarStatusCandidato(candidato.id, status);
    this.candidatoAberto.update((atual) => (atual && atual.id === candidato.id ? { ...atual, status } : atual));
  }

  protected baixarCurriculo(candidato: Candidato): void {
    this.analiseCurriculo.baixarCurriculo(candidato);
  }

  protected dataFormatada(criadoEm: string): string {
    return new Date(criadoEm).toLocaleDateString('pt-BR');
  }

  protected definirArquivos(arquivos: File[]): void {
    this.arquivosSelecionados.set(arquivos);
  }

  protected fecharDetalhe(): void {
    this.candidatoAberto.set(null);
  }

  protected fecharDialogAnalise(): void {
    this.dialogAnaliseAberto.set(false);
  }

  protected iniciarAnalises(): void {
    for (const arquivo of this.arquivosSelecionados()) {
      this.analiseCurriculo.iniciarAnalise(arquivo);
    }
    this.dialogAnaliseAberto.set(false);
  }

  protected resumoTruncado(candidato: Candidato): string {
    const resumo = candidato.resumo_perfil;
    return resumo.length > LIMITE_RESUMO_TRUNCADO ? `${resumo.slice(0, LIMITE_RESUMO_TRUNCADO)}...` : resumo;
  }

  protected rotuloStatus(status: StatusCandidato): string {
    return ROTULOS_STATUS[status];
  }
}
