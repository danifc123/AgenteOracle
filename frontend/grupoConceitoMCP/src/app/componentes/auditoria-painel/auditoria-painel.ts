import { Component, inject } from '@angular/core';
import { AchadoAuditoria, Auditoria } from '../../servicos/auditoria';
import { Botao } from '../botao/botao';
import { Dialog } from '../dialog/dialog';

@Component({
  selector: 'app-auditoria-painel',
  imports: [Botao, Dialog],
  templateUrl: './auditoria-painel.html',
  styleUrl: './auditoria-painel.scss'
})
export class AuditoriaPainel {
  protected readonly auditoria = inject(Auditoria);

  protected fechar(): void {
    this.auditoria.fechar();
  }

  protected rodar(): void {
    this.auditoria.buscar();
  }

  protected dispensar(achado: AchadoAuditoria): void {
    this.auditoria.dispensar(achado);
  }

  protected chaveAchado(achado: AchadoAuditoria): string {
    return `${achado.modulo}|${achado.view}|${achado.campo}|${achado.valor}`;
  }
}
