import { Component, computed, inject, signal } from '@angular/core';
import { Botao } from '../../../../componentes/botao/botao';
import { DetalheCandidato } from '../../../../componentes/detalhe-candidato/detalhe-candidato';
import { Dialog } from '../../../../componentes/dialog/dialog';
import { EstadoVazio } from '../../../../componentes/estado-vazio/estado-vazio';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { SeletorArquivoCurriculo } from '../../../../componentes/seletor-arquivo-curriculo/seletor-arquivo-curriculo';
import {
  AnaliseCurriculo,
  Candidato,
  ROTULOS_SENIORIDADE,
  ROTULOS_STATUS,
  StatusCandidato,
} from '../../../../servicos/analise-curriculo';
import { BuscaCandidatos, ResultadoBusca } from '../../../../servicos/busca-candidatos';

const LIMITE_RESUMO_TRUNCADO = 140;

type ModoAnaliseCandidato = 'lista' | 'busca';

/** MÓDULO RH — TELA "ANÁLISE DE CANDIDATO" (2026-08)
 *
 * Fundida com a antiga tela "Selecionar Candidato" numa tela só, mesmo
 * padrão de abas de `Repescagem` (`modo`, mesma ideia de
 * `ConfiguracoesUsuario.secaoAtiva`) — RH sobe currículo e busca por vaga
 * no mesmo lugar, em vez de duas telas separadas competindo por rota
 * própria na sidebar.
 *
 * Substitui a tela antiga "DNA Agro" — não existe mais vaga cadastrada nem
 * score fixo contra dimensões genéricas. O RH sobe um ou mais currículos de
 * uma vez (`SeletorArquivoCurriculo` em modo múltiplo); cada arquivo
 * dispara sua própria análise em segundo plano (`iniciarAnalises` chama
 * `AnaliseCurriculo.iniciarAnalise` uma vez por arquivo), o dialog fecha na
 * hora, e cada currículo avisa via toast quando termina, independente dos
 * outros do mesmo lote. Todo candidato analisado com sucesso entra no pool
 * (aba "Candidatos Ativos"); a busca por candidato ideal pra uma vaga
 * (aba "Buscar por Vaga", RAG — `agent/rh/busca_candidatos.py`) acontece
 * depois, sob demanda, sobre esse mesmo pool.
 */
@Component({
  selector: 'app-analise-candidato',
  imports: [Botao, DetalheCandidato, Dialog, EstadoVazio, ModuloHeader, SeletorArquivoCurriculo],
  templateUrl: './analise-candidato.html',
  styleUrl: './analise-candidato.scss',
})
export class AnaliseCandidato {
  protected readonly analiseCurriculo = inject(AnaliseCurriculo);
  protected readonly busca = inject(BuscaCandidatos);

  protected readonly modo = signal<ModoAnaliseCandidato>('lista');
  protected readonly dialogAnaliseAberto = signal(false);
  protected readonly arquivosSelecionados = signal<File[]>([]);
  protected readonly candidatoAberto = signal<Candidato | null>(null);
  protected readonly descricao = signal('');
  protected readonly buscaFeita = signal(false);
  protected readonly resultadoAberto = signal<ResultadoBusca | null>(null);

  protected readonly candidatosAtivos = computed(() =>
    this.analiseCurriculo.candidatos().filter((candidato) => candidato.status === 'ativo'),
  );

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

  protected abrirPerfil(resultado: ResultadoBusca): void {
    this.resultadoAberto.set(resultado);
  }

  protected atualizarStatus(candidato: Candidato, status: StatusCandidato): void {
    this.analiseCurriculo.atualizarStatusCandidato(candidato.id, status);
    this.candidatoAberto.update((atual) => (atual && atual.id === candidato.id ? { ...atual, status } : atual));
  }

  protected baixarCurriculo(candidato: Candidato): void {
    this.analiseCurriculo.baixarCurriculo(candidato);
  }

  protected baixarCurriculoResultado(resultado: ResultadoBusca): void {
    this.analiseCurriculo.baixarCurriculo({ id: resultado.candidato_id, nome: resultado.nome });
  }

  protected buscar(): void {
    const texto = this.descricao().trim();
    if (!texto) {
      return;
    }
    this.buscaFeita.set(true);
    this.busca.buscar(texto);
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

  protected fecharPerfil(): void {
    this.resultadoAberto.set(null);
  }

  protected iniciarAnalises(): void {
    for (const arquivo of this.arquivosSelecionados()) {
      this.analiseCurriculo.iniciarAnalise(arquivo);
    }
    this.dialogAnaliseAberto.set(false);
  }

  protected percentual(similaridade: number): string {
    return `${Math.round(similaridade * 100)}%`;
  }

  protected resumoTruncado(candidato: Candidato): string {
    const resumo = candidato.resumo_perfil;
    return resumo.length > LIMITE_RESUMO_TRUNCADO ? `${resumo.slice(0, LIMITE_RESUMO_TRUNCADO)}...` : resumo;
  }

  protected rotuloSenioridade(resultado: ResultadoBusca): string {
    return ROTULOS_SENIORIDADE[resultado.nivel_senioridade];
  }

  protected rotuloStatus(status: StatusCandidato): string {
    return ROTULOS_STATUS[status];
  }
}
