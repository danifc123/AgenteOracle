import { HttpClient } from '@angular/common/http';
import { Component, computed, inject, signal, viewChild } from '@angular/core';
import { MCP_API_BASE_URL } from '../../app-config';
import { Botao } from '../../componentes/botao/botao';
import { ModuloHeader } from '../../componentes/modulo-header/modulo-header';
import { SeletorArquivoExcel } from '../../componentes/seletor-arquivo-excel/seletor-arquivo-excel';
import { baixarBlob, extrairNomeArquivo } from '../../servicos/download-arquivo';

type TipoAnaliseColunas = 'identicas' | 'parcial' | 'nenhuma';

interface AnaliseColunas {
  tipo: TipoAnaliseColunas;
  colunas1: string[];
  colunas2: string[];
  colunas_comuns: string[];
}

@Component({
  selector: 'app-juntar-excel',
  imports: [Botao, ModuloHeader, SeletorArquivoExcel],
  templateUrl: './juntar-excel.html',
  styleUrl: './juntar-excel.scss',
})
export class JuntarExcel {
  private readonly http = inject(HttpClient);

  private readonly seletor1 = viewChild.required<SeletorArquivoExcel>('seletor1');
  private readonly seletor2 = viewChild.required<SeletorArquivoExcel>('seletor2');

  protected readonly arquivo1 = signal<File | null>(null);
  protected readonly arquivo2 = signal<File | null>(null);
  protected readonly enviando = signal(false);
  protected readonly erro = signal<string | null>(null);
  protected readonly concluido = signal(false);

  protected readonly analise = signal<AnaliseColunas | null>(null);
  protected readonly analisando = signal(false);

  protected readonly prontoParaEnviar = computed(
    () => this.arquivo1() !== null && this.arquivo2() !== null,
  );

  private atualizarAnalise(): void {
    const arquivo1 = this.arquivo1();
    const arquivo2 = this.arquivo2();
    this.analise.set(null);

    if (!arquivo1 || !arquivo2) {
      this.analisando.set(false);
      return;
    }

    this.analisando.set(true);

    const formData = new FormData();
    formData.append('arquivo1', arquivo1);
    formData.append('arquivo2', arquivo2);

    this.http
      .post<AnaliseColunas>(`${MCP_API_BASE_URL}/api/ferramentas/juntar-excel/analisar`, formData)
      .subscribe({
        next: (resultado) => {
          this.analise.set(resultado);
          this.analisando.set(false);
        },
        error: () => {
          this.analisando.set(false);
        },
      });
  }

  definirArquivo1(arquivo: File | null): void {
    this.arquivo1.set(arquivo);
    this.concluido.set(false);
    this.atualizarAnalise();
  }

  definirArquivo2(arquivo: File | null): void {
    this.arquivo2.set(arquivo);
    this.concluido.set(false);
    this.atualizarAnalise();
  }

  juntar(): void {
    const arquivo1 = this.arquivo1();
    const arquivo2 = this.arquivo2();
    if (!arquivo1 || !arquivo2 || this.enviando()) {
      return;
    }

    this.enviando.set(true);
    this.erro.set(null);
    this.concluido.set(false);

    const formData = new FormData();
    formData.append('arquivo1', arquivo1);
    formData.append('arquivo2', arquivo2);

    this.http
      .post(`${MCP_API_BASE_URL}/api/ferramentas/juntar-excel`, formData, {
        observe: 'response',
        responseType: 'blob',
      })
      .subscribe({
        next: (resposta) => {
          const blob = resposta.body;
          this.enviando.set(false);
          if (!blob) {
            return;
          }

          const nomeArquivo = extrairNomeArquivo(
            resposta.headers.get('content-disposition'),
            'planilhas_combinadas.xlsx',
          );
          baixarBlob(blob, nomeArquivo);
          this.concluido.set(true);
        },
        error: () => {
          this.erro.set(
            'Não foi possível juntar as planilhas. Verifique se os arquivos são .xlsx válidos.',
          );
          this.enviando.set(false);
        },
      });
  }

  reiniciar(): void {
    this.seletor1().remover();
    this.seletor2().remover();
    this.concluido.set(false);
    this.erro.set(null);
  }
}
