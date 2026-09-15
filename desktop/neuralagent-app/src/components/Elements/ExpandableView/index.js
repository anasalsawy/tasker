import React, { useState } from 'react';
import {
  ExpandableViewContainer,
  ExpandableViewDiv,
  ActionsContainer,
  ArrowIcon,
  Action
} from './Elements';
import { Text } from '../../Typography';
import { useSelector } from 'react-redux';
import { FiChevronDown, FiChevronUp } from 'react-icons/fi';
import { IconButton } from '../Button';
import { Chip } from '../Chip';


function ExpandableView({
  title,
  child,
  padding='18px 10px',
  color='transparent',
  isInitiallyOpen=false,
  actions=[],
  style={},
  chip=null,
  chipColor='var(--danger-color)',
}) {

  const [isOpen, setOpen] = useState(isInitiallyOpen);

  const isRTL = useSelector(state => state.isRTL);

  const onActionClick = (e, action) => {
    e.stopPropagation();
    action.onClick();
  };

  return (
    <ExpandableViewContainer color={color} style={style}>
      <ExpandableViewDiv color={color} onClick={() => setOpen(!isOpen)} padding={padding}>
        <Text fontSize="17px" color="rgba(0, 0, 0, 0.85)" fontWeight="500">
          {title}
        </Text>
        {
          chip !== null ?
          <Chip style={{margin: '0px 10px'}} color={chipColor} borderRadius={10} padding='5px 10px' dark fontSize='13px'>
            {chip}
          </Chip> : <></>
        }
        <ActionsContainer isRTL={isRTL}>
          {actions.map((action, i) => {
            return <Action key={'action__' + i}>
              <IconButton onClick={(e) => onActionClick(e, action)} color={action.color !== null ? action.color : 'rgba(0, 0, 0, 0.85)'}>
                {action.icon}
              </IconButton>
            </Action>;
          })}
          <ArrowIcon color="rgba(0, 0, 0, 0.85)">
            {
              isOpen ? <FiChevronUp /> : <FiChevronDown />
            }
          </ArrowIcon>
        </ActionsContainer>
      </ExpandableViewDiv>
      {
        isOpen ?
        <div style={{marginTop: '0px'}}>
          {child}
        </div> : <></>
      }
    </ExpandableViewContainer>
  );
}

export default ExpandableView;